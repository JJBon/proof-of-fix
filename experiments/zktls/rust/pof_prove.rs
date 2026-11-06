// The prover for the zkTLS spike (proof-of-fix#135). It reads one raw, already-signed HTTP request from stdin (the
// orchestrator signs it; this program never prints or stores it), sends it to the provider over a TLS connection
// run jointly with a verifier (MPC-TLS, or proxy mode), and then either:
//   --attest: gets a signed attestation from a notary and builds a presentation that reveals everything except the
//             values of the --hide headers (the credentials); or
//   (default): reveals the same ranges interactively to a verifier that signs nothing (the public demo verifier).
// It writes one JSON line of results to stdout. In the interactive mode it first writes a {"event":"reveal"} line
// with the ranges, which the orchestrator forwards to the public verifier's session.
//
// Nothing secret reaches disk: the connection secrets stay in memory, and only the attestation and the presentation
// (which hides the --hide header values) are written.

use std::{future::IntoFuture, ops::Range, time::Instant};

use anyhow::{Result, anyhow};
use clap::Parser;
use futures::io::{AsyncReadExt as _, AsyncWriteExt as _};
use tokio::io::AsyncReadExt as _;
use tokio_util::compat::TokioAsyncReadCompatExt;

use tlsn::{
    Session,
    attestation::{
        Attestation, CryptoProvider,
        presentation::Presentation,
        request::{Request as AttestationRequest, RequestConfig},
        signing::SignatureAlgId,
    },
    config::{
        prove::ProveConfig,
        prover::ProverConfig,
        tls::TlsClientConfig,
        tls_commit::{mpc::MpcTlsConfig, proxy::ProxyTlsConfig},
    },
    connection::{DnsName, HandshakeData, ServerName},
    hash::HashAlgId,
    prover::ProverOutput,
    rangeset::set::RangeSet,
    transcript::{TranscriptCommitConfig, TranscriptCommitmentKind},
    webpki::RootCertStore,
};

#[path = "pof_common.rs"]
mod common;
use common::{Counting, complement, header_value_ranges, ranges_json};

#[derive(Parser, Debug)]
struct Args {
    /// The notary or verifier, as host:port over plain TCP (the public verifier is reached through a local bridge).
    #[arg(long)]
    verifier: String,
    #[arg(long, default_value = "mpc")]
    mode: String,
    #[arg(long, default_value = "bedrock-runtime.us-east-1.amazonaws.com")]
    server_name: String,
    #[arg(long, default_value_t = 4096)]
    max_sent: usize,
    #[arg(long, default_value_t = 4096)]
    max_recv: usize,
    /// MPC mode: the number of sent records to preprocess (the release's default grows with --max-sent).
    #[arg(long)]
    max_sent_records: Option<usize>,
    /// Notary flow: get a signed attestation and write <out>.attestation.tlsn and <out>.presentation.tlsn.
    #[arg(long)]
    attest: bool,
    #[arg(long, default_value = "")]
    out: String,
    /// Header whose value is hidden from the verifier and from the presentation (repeatable).
    #[arg(long = "hide")]
    hide: Vec<String>,
}

fn secs(t: Instant) -> f64 {
    (t.elapsed().as_secs_f64() * 1000.0).round() / 1000.0
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_writer(std::io::stderr).init();
    let args = Args::parse();
    let mut request = Vec::new();
    tokio::io::stdin().read_to_end(&mut request).await?;
    if request.is_empty() {
        return Err(anyhow!("no request on stdin"));
    }
    match run(&args, request).await {
        Ok(v) => {
            println!("{}", serde_json::json!({"event": "result", "ok": true, "result": v}));
            Ok(())
        }
        Err(e) => {
            println!("{}", serde_json::json!({"event": "result", "ok": false, "error": format!("{e:#}")}));
            Err(e)
        }
    }
}

/// Ranges of `recv` that repeat 16 or more bytes of a hidden value (checked at every 8th offset of the value).
fn echoes(sent: &[u8], hidden: &[Range<usize>], recv: &[u8]) -> Vec<Range<usize>> {
    let mut out: Vec<Range<usize>> = Vec::new();
    for r in hidden {
        let v = &sent[r.clone()];
        let mut k = 0;
        while k + 16 <= v.len() {
            let probe = &v[k..k + 16];
            let mut i = 0;
            while i + 16 <= recv.len() {
                if &recv[i..i + 16] == probe {
                    let (mut a, mut b, mut va, mut vb) = (i, i + 16, k, k + 16);
                    while a > 0 && va > 0 && recv[a - 1] == v[va - 1] {
                        a -= 1;
                        va -= 1;
                    }
                    while b < recv.len() && vb < v.len() && recv[b] == v[vb] {
                        b += 1;
                        vb += 1;
                    }
                    out.push(a..b);
                    i = b;
                } else {
                    i += 1;
                }
            }
            k += 8;
        }
    }
    out.sort_by_key(|r| r.start);
    let mut merged: Vec<Range<usize>> = Vec::new();
    for r in out {
        match merged.last_mut() {
            Some(last) if r.start <= last.end => last.end = last.end.max(r.end),
            _ => merged.push(r),
        }
    }
    merged
}

async fn exchange<C>(mut conn: C, request: &[u8]) -> Result<Vec<u8>>
where
    C: futures::AsyncRead + futures::AsyncWrite + Unpin,
{
    conn.write_all(request).await?;
    conn.flush().await?;
    // With deferred decryption the plaintext arrives once the server closes the connection ("Connection: close").
    let mut response = Vec::new();
    tokio::time::timeout(std::time::Duration::from_secs(180), conn.read_to_end(&mut response))
        .await
        .map_err(|_| anyhow!("no response within 180 s"))??;
    Ok(response)
}

async fn run(args: &Args, request: Vec<u8>) -> Result<serde_json::Value> {
    let t0 = Instant::now();
    let tcp = tokio::net::TcpStream::connect(&args.verifier).await?;
    let (tcp, counters) = Counting::new(tcp);
    let session = Session::new(tcp.compat());
    let (driver, mut handle) = session.split();
    let driver_task = tokio::spawn(driver);

    let tls_config = TlsClientConfig::builder()
        .server_name(ServerName::Dns(args.server_name.as_str().try_into()?))
        .root_store(RootCertStore::mozilla())
        .build()?;
    let new_prover = handle.new_prover(ProverConfig::builder().build()?)?;

    let (setup_s, response, prover, response_s) = match args.mode.as_str() {
        "mpc" => {
            let mut mpc = MpcTlsConfig::builder().max_sent_data(args.max_sent).max_recv_data(args.max_recv);
            if let Some(n) = args.max_sent_records {
                mpc = mpc.max_sent_records(n);
            }
            let p = new_prover.commit(mpc.build()?).await?;
            let setup_s = secs(t0);
            let server = tokio::net::TcpStream::connect((args.server_name.as_str(), 443)).await?;
            let (conn, fut) = p.connect(tls_config, server.compat())?;
            let task = tokio::spawn(fut.into_future());
            let t1 = Instant::now();
            let response = exchange(conn, &request).await?;
            let prover = task.await??;
            (setup_s, response, prover, secs(t1))
        }
        "proxy" => {
            let p = new_prover
                .commit(ProxyTlsConfig::builder().server_name(DnsName::try_from(args.server_name.as_str())?).build()?)
                .await?;
            let setup_s = secs(t0);
            let (conn, fut) = p.connect(tls_config)?;
            let task = tokio::spawn(fut.into_future());
            let t1 = Instant::now();
            let response = exchange(conn, &request).await?;
            let prover = task.await??;
            (setup_s, response, prover, secs(t1))
        }
        m => return Err(anyhow!("unknown mode {m}")),
    };
    let mut prover = prover;

    let sent_len = prover.transcript().sent().len();
    let recv_len = prover.transcript().received().len();
    let tls_version = format!("{:?}", prover.tls_transcript().version());
    let hidden = header_value_ranges(prover.transcript().sent(), &args.hide);
    if hidden.len() < args.hide.len() {
        return Err(anyhow!("not every --hide header was found in the request"));
    }
    let reveal_sent_v: Vec<Range<usize>> = complement(sent_len, &hidden);
    let reveal_sent = RangeSet::from(reveal_sent_v.clone());

    // What the response reveals. A provider's error can quote the request (Bedrock's signature error quotes the
    // canonical request, session token included), so a response that isn't 2xx reveals only its status line, and
    // any echo of a hidden value is hidden wherever it appears.
    let recv = prover.transcript().received().to_vec();
    let status_end = recv.windows(2).position(|w| w == b"\r\n").unwrap_or(recv.len());
    let status = String::from_utf8_lossy(&recv[..status_end]).to_string();
    let mut hidden_recv = echoes(prover.transcript().sent(), &hidden, &recv);
    let success = status.starts_with("HTTP/1.1 2");
    if !success {
        hidden_recv.push(status_end..recv_len);
    }
    let reveal_recv_v = complement(recv_len, &hidden_recv);
    let reveal_recv = RangeSet::from(reveal_recv_v.clone());
    let mut shown = recv.clone();
    for r in &hidden_recv {
        shown[r.clone()].fill(b'X');
    }
    drop(response);
    let head_end = shown.windows(4).position(|w| w == b"\r\n\r\n").map_or(shown.len(), |p| p + 4);
    let body = String::from_utf8_lossy(&shown[head_end.min(shown.len())..]).to_string();

    let t2 = Instant::now();
    let mut out = serde_json::json!({
        "mode": args.mode, "server_name": args.server_name, "tls_version": tls_version,
        "max_sent": args.max_sent, "max_recv": args.max_recv, "sent_len": sent_len, "recv_len": recv_len,
        "hidden_sent": ranges_json(&hidden), "revealed_sent": ranges_json(&reveal_sent_v),
        "hidden_recv": ranges_json(&hidden_recv), "revealed_recv": ranges_json(&reveal_recv_v),
        "status": status, "response_body": body,
        "setup_s": setup_s, "tls_exchange_s": response_s,
    });

    if args.attest {
        let mut cb = TranscriptCommitConfig::builder(prover.transcript());
        cb.default_kind(TranscriptCommitmentKind::Hash { alg: HashAlgId::SHA256 });
        cb.commit_sent(&reveal_sent)?;
        cb.commit_recv(&reveal_recv)?;
        let commit = cb.build()?;

        let mut rb = RequestConfig::builder();
        rb.signature_alg(SignatureAlgId::SECP256K1ETH).hash_alg(HashAlgId::KECCAK256).transcript_commit(commit);
        let request_config = rb.build()?;

        let mut pb = ProveConfig::builder(prover.transcript());
        if let Some(c) = request_config.transcript_commit() {
            pb.transcript_commit(c.clone());
        }
        let ProverOutput { transcript_commitments, transcript_secrets, .. } = prover.prove(&pb.build()?).await?;
        let prove_s = secs(t2);

        let transcript = prover.transcript().clone();
        let tls = prover.tls_transcript().clone();
        prover.close().await?;

        let t3 = Instant::now();
        let mut ab = AttestationRequest::builder(&request_config);
        ab.server_name(ServerName::Dns(args.server_name.as_str().try_into()?))
            .handshake_data(HandshakeData {
                certs: tls.server_cert_chain().ok_or_else(|| anyhow!("no cert chain"))?.to_vec(),
                sig: tls.server_signature().ok_or_else(|| anyhow!("no server signature"))?.clone(),
                binding: tls.certificate_binding().clone(),
            })
            .transcript(transcript)
            .transcript_commitments(transcript_secrets, transcript_commitments);
        let provider = CryptoProvider::default();
        let (att_request, secrets) = ab.build(&provider)?;

        handle.close();
        let mut socket = driver_task.await??;
        socket.write_all(&bincode::serialize(&att_request)?).await?;
        socket.close().await?;
        let mut att_bytes = Vec::new();
        socket.read_to_end(&mut att_bytes).await?;
        let attestation: Attestation = bincode::deserialize(&att_bytes)?;
        att_request.validate(&attestation, &provider)?;
        let attest_s = secs(t3);

        let t4 = Instant::now();
        let mut tb = secrets.transcript_proof_builder();
        tb.reveal_sent(&reveal_sent)?;
        tb.reveal_recv(&reveal_recv)?;
        let transcript_proof = tb.build()?;
        let mut presb = attestation.presentation_builder(&provider);
        presb.identity_proof(secrets.identity_proof()).transcript_proof(transcript_proof);
        let presentation: Presentation = presb.build()?;
        let pres_bytes = bincode::serialize(&presentation)?;
        let present_s = secs(t4);

        if !args.out.is_empty() {
            std::fs::write(format!("{}.attestation.tlsn", args.out), &att_bytes)?;
            std::fs::write(format!("{}.presentation.tlsn", args.out), &pres_bytes)?;
        }
        out["prove_s"] = prove_s.into();
        out["attest_s"] = attest_s.into();
        out["present_s"] = present_s.into();
        out["attestation_bytes"] = att_bytes.len().into();
        out["presentation_bytes"] = pres_bytes.len().into();
    } else {
        println!(
            "{}",
            serde_json::json!({"event": "reveal", "sent": ranges_json(&reveal_sent_v), "recv": ranges_json(&reveal_recv_v)})
        );
        let mut pb = ProveConfig::builder(prover.transcript());
        pb.server_identity();
        pb.reveal_sent(&reveal_sent)?;
        pb.reveal_recv(&reveal_recv)?;
        prover.prove(&pb.build()?).await?;
        out["prove_s"] = secs(t2).into();
        prover.close().await?;
        handle.close();
        driver_task.await??;
    }
    out["total_s"] = secs(t0).into();
    out["verifier_bytes_up"] = counters.written().into();
    out["verifier_bytes_down"] = counters.read().into();
    Ok(out)
}
