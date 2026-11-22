// Offline verifier and receipt exporter for the zkTLS spike (proof-of-fix#135). It verifies a presentation with the
// pinned tlsn release (notary signature, Merkle root, server certificate chain and handshake signature against the
// Mozilla roots at the connection's time, transcript openings) and makes no network connection.
//
// With --receipt it also writes the parts a level C receipt would carry, as JSON, so a check without Rust
// (tests/test_zktls_receipt.py) can redo every step except the certificate chain: the notary key and signature, the
// BCS-encoded header and body, the domain separators, the hash openings and the revealed transcript.
//
//   pof_verify <presentation.tlsn> [--receipt receipt.json] [--expect-server bedrock-runtime.us-east-1.amazonaws.com]

use std::time::Instant;

use anyhow::{Result, anyhow};
use clap::Parser;

use tlsn::{
    attestation::{
        CryptoProvider,
        presentation::{Presentation, PresentationOutput},
    },
    transcript::hash::PlaintextHashSecret,
};

#[derive(Parser, Debug)]
struct Args {
    presentation: String,
    #[arg(long, default_value = "")]
    receipt: String,
    #[arg(long, default_value = "")]
    expect_server: String,
}

fn domain(name: &str) -> String {
    hex::encode(&blake3::hash(name.as_bytes()).as_bytes()[..16])
}

fn main() -> Result<()> {
    let args = Args::parse();
    let bytes = std::fs::read(&args.presentation)?;
    let t0 = Instant::now();
    let presentation: Presentation = bincode::deserialize(&bytes)?;
    let as_json = serde_json::to_value(&presentation)?;
    let key = presentation.verifying_key().clone();

    let PresentationOutput { attestation, server_name, connection_info, transcript, .. } =
        presentation.verify(&CryptoProvider::default()).map_err(|e| anyhow!("verification failed: {e}"))?;
    let verify_s = t0.elapsed().as_secs_f64();

    let server = match server_name {
        Some(tlsn::connection::ServerName::Dns(n)) => n.as_str().to_string(),
        None => return Err(anyhow!("the presentation doesn't reveal the server")),
    };
    if !args.expect_server.is_empty() && server != args.expect_server {
        return Err(anyhow!("server is {server}, expected {}", args.expect_server));
    }
    let transcript = transcript.ok_or_else(|| anyhow!("no transcript in the presentation"))?;
    let ranges = |s: &tlsn::rangeset::set::RangeSet<usize>| -> Vec<[usize; 2]> {
        s.iter().map(|r| [r.start, r.end]).collect()
    };

    eprintln!(
        "verified offline in {verify_s:.3} s: server {server}, {:?}, time {}, sent {} B ({} revealed), received {} B; \
         notary key {} ({})",
        connection_info.version,
        connection_info.time,
        connection_info.transcript_length.sent,
        transcript.sent_authed().len(),
        connection_info.transcript_length.received,
        hex::encode(&key.data),
        key.alg,
    );

    if args.receipt.is_empty() {
        return Ok(());
    }
    let secrets: Vec<PlaintextHashSecret> = serde_json::from_value(as_json["transcript"]["hash_secrets"].clone())?;
    let openings: Vec<serde_json::Value> = secrets
        .iter()
        .map(|s| {
            serde_json::json!({
                "direction": format!("{:?}", s.direction),
                "ranges": ranges(&s.idx),
                "alg": s.alg.as_u8(),
                "blinder": hex::encode(s.blinder.as_bytes()),
            })
        })
        .collect();

    // The domain separators: tlsn hashes each attestation field as H(domain || BCS(field)), where domain is the first
    // 16 bytes of blake3(the type's name as written in tlsn's source).
    let domains = serde_json::json!({
        "VerifyingKey": domain(stringify!(VerifyingKey)),
        "ConnectionInfo": domain(stringify!(tlsn_core::connection::ConnectionInfo)),
        "ServerEphemKey": domain(stringify!(tlsn_core::connection::ServerEphemKey)),
        "ServerCertCommitment": domain(stringify!(ServerCertCommitment)),
        "Extension": domain(stringify!(Extension)),
        "TranscriptCommitment": domain(stringify!(tlsn_core::transcript::TranscriptCommitment)),
    });

    let receipt = serde_json::json!({
        "format": "pof-zktls-receipt/1",
        "implementation": "tlsn v0.1.0-alpha.15",
        "server_name": server,
        "notary_key": {"alg": key.alg.as_u8(), "sec1": hex::encode(&key.data)},
        "signature": {"alg": attestation.signature.alg.as_u8(), "data": hex::encode(&attestation.signature.data)},
        "header_bcs": hex::encode(bcs::to_bytes(&attestation.header)?),
        "body_bcs": hex::encode(bcs::to_bytes(&attestation.body)?),
        "domains": domains,
        "connection": {
            "time": connection_info.time,
            "tls_version": format!("{:?}", connection_info.version),
            "sent_len": connection_info.transcript_length.sent,
            "recv_len": connection_info.transcript_length.received,
        },
        "sent": {"bytes": hex::encode(transcript.sent_unsafe()), "authed": ranges(transcript.sent_authed())},
        "recv": {"bytes": hex::encode(transcript.received_unsafe()), "authed": ranges(transcript.received_authed())},
        "openings": openings,
        "rust_verify_s": (verify_s * 1000.0).round() / 1000.0,
    });
    std::fs::write(&args.receipt, serde_json::to_string_pretty(&receipt)? + "\n")?;
    Ok(())
}
