// A notary for the zkTLS spike (proof-of-fix#135), built from the tlsn release's attestation example: it acts as
// the TLS verifier (MPC-TLS or proxy mode), then signs an attestation with a secp256k1 key in the "secp256k1eth"
// scheme (keccak-256 of the BCS-encoded header, r || s || v), which a contract can check with ecrecover.
//
// It listens on 127.0.0.1 only, and refuses sessions above its data caps.
//
//   pof_notary --listen 127.0.0.1:7150 --key-file <hex secp256k1 secret> [--max-sent 8192 --max-recv 16384]

use std::time::Instant;

use anyhow::{Result, anyhow};
use clap::Parser;
use futures::io::{AsyncReadExt as _, AsyncWriteExt as _};
use tokio::net::TcpListener;
use tokio_util::compat::TokioAsyncReadCompatExt;

use tlsn::{
    Session,
    attestation::{Attestation, AttestationConfig, CryptoProvider, request::Request as AttestationRequest},
    config::verifier::VerifierConfig,
    connection::{CertBinding, ConnectionInfo, TranscriptLength},
    transcript::ContentType,
    verifier::{VerifierCommitStart, VerifierOutput},
    webpki::RootCertStore,
};

#[derive(Parser, Debug)]
struct Args {
    #[arg(long, default_value = "127.0.0.1:7150")]
    listen: String,
    #[arg(long)]
    key_file: String,
    #[arg(long, default_value_t = 8192)]
    max_sent: usize,
    #[arg(long, default_value_t = 16384)]
    max_recv: usize,
    /// Exit after this many sessions (0 = run until killed).
    #[arg(long, default_value_t = 0)]
    sessions: usize,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_writer(std::io::stderr).init();
    let args = Args::parse();
    if !args.listen.starts_with("127.0.0.1:") {
        return Err(anyhow!("the spike's notary listens on 127.0.0.1 only"));
    }
    let key = hex::decode(std::fs::read_to_string(&args.key_file)?.trim())?;
    let mut provider = CryptoProvider::default();
    provider.signer.set_secp256k1eth(&key)?;
    let listener = TcpListener::bind(&args.listen).await?;
    eprintln!("notary listening on {} (secp256k1eth signer)", args.listen);

    let mut served = 0;
    loop {
        let (socket, peer) = listener.accept().await?;
        if !peer.ip().is_loopback() {
            continue;
        }
        let started = Instant::now();
        match notarize(socket, &provider, args.max_sent, args.max_recv).await {
            Ok((size, mode)) => eprintln!(
                "{}",
                serde_json::json!({"event": "attested", "mode": mode, "attestation_bytes": size,
                                   "seconds": started.elapsed().as_secs_f64()})
            ),
            Err(e) => eprintln!("{}", serde_json::json!({"event": "failed", "error": format!("{e:#}")})),
        }
        served += 1;
        if args.sessions != 0 && served >= args.sessions {
            return Ok(());
        }
    }
}

async fn notarize(
    socket: tokio::net::TcpStream,
    provider: &CryptoProvider,
    max_sent: usize,
    max_recv: usize,
) -> Result<(usize, &'static str)> {
    let session = Session::new(socket.compat());
    let (driver, mut handle) = session.split();
    let driver_task = tokio::spawn(driver);

    let config = VerifierConfig::builder().root_store(RootCertStore::mozilla()).build()?;
    let (verifier, mode) = match handle.new_verifier(config)?.commit().await? {
        VerifierCommitStart::Mpc(v) => {
            let c = v.config();
            if c.max_sent_data() > max_sent || c.max_recv_data() > max_recv {
                let msg = format!("asks {}/{} bytes, caps are {max_sent}/{max_recv}", c.max_sent_data(), c.max_recv_data());
                v.reject(Some(&msg)).await?;
                return Err(anyhow!(msg));
            }
            (v.accept().await?.run().await?, "mpc")
        }
        VerifierCommitStart::Proxy(v) => {
            let host = v.config().server_name().as_str().to_string();
            let server = tokio::net::TcpStream::connect((host.as_str(), 443)).await?;
            (v.accept().await?.run(server.compat()).await?, "proxy")
        }
    };

    let (VerifierOutput { transcript_commitments, .. }, verifier) = verifier.verify().await?.accept().await?;
    let tls = verifier.tls_transcript().clone();
    verifier.close().await?;

    let app_len = |records: &[tlsn::transcript::Record]| -> u32 {
        records.iter().filter(|r| r.typ == ContentType::ApplicationData).map(|r| r.ciphertext.len()).sum::<usize>() as u32
    };
    let (sent_len, recv_len) = (app_len(tls.sent()), app_len(tls.recv()));
    if sent_len as usize > max_sent || recv_len as usize > max_recv {
        return Err(anyhow!("transcript {sent_len}/{recv_len} bytes is above the caps"));
    }

    handle.close();
    let mut socket = driver_task.await??;

    let mut request_bytes = Vec::new();
    socket.read_to_end(&mut request_bytes).await?;
    let request: AttestationRequest = bincode::deserialize(&request_bytes)?;

    let mut b = AttestationConfig::builder();
    b.supported_signature_algs(Vec::from_iter(provider.signer.supported_algs()));
    let att_config = b.build()?;

    let CertBinding::V1_2(binding) = tls.certificate_binding() else {
        return Err(anyhow!("unsupported certificate binding (only TLS 1.2 is supported)"));
    };
    let mut builder = Attestation::builder(&att_config).accept_request(request)?;
    builder
        .connection_info(ConnectionInfo {
            time: tls.time(),
            version: tls.version(),
            transcript_length: TranscriptLength { sent: sent_len, received: recv_len },
        })
        .server_ephemeral_key(binding.server_ephemeral_key.clone())
        .transcript_commitments(transcript_commitments);
    let attestation = builder.build(provider)?;

    let bytes = bincode::serialize(&attestation)?;
    socket.write_all(&bytes).await?;
    socket.close().await?;
    Ok((bytes.len(), mode))
}
