// Shared code for the zkTLS spike's tools (proof-of-fix#135): a byte-counting stream (the prover-notary traffic
// is part of the cost) and the request's redaction ranges.

use std::{
    io,
    ops::Range,
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
    task::{Context, Poll},
};

use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

/// Bytes written to and read from the wrapped stream.
#[derive(Clone, Default)]
pub struct Counters {
    pub written: Arc<AtomicU64>,
    pub read: Arc<AtomicU64>,
}

impl Counters {
    pub fn written(&self) -> u64 {
        self.written.load(Ordering::Relaxed)
    }
    pub fn read(&self) -> u64 {
        self.read.load(Ordering::Relaxed)
    }
}

pub struct Counting<S> {
    inner: S,
    counters: Counters,
}

impl<S> Counting<S> {
    pub fn new(inner: S) -> (Self, Counters) {
        let counters = Counters::default();
        (Self { inner, counters: counters.clone() }, counters)
    }
}

impl<S: AsyncRead + Unpin> AsyncRead for Counting<S> {
    fn poll_read(mut self: Pin<&mut Self>, cx: &mut Context<'_>, buf: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
        let before = buf.filled().len();
        let res = Pin::new(&mut self.inner).poll_read(cx, buf);
        let n = buf.filled().len() - before;
        self.counters.read.fetch_add(n as u64, Ordering::Relaxed);
        res
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for Counting<S> {
    fn poll_write(mut self: Pin<&mut Self>, cx: &mut Context<'_>, buf: &[u8]) -> Poll<io::Result<usize>> {
        let res = Pin::new(&mut self.inner).poll_write(cx, buf);
        if let Poll::Ready(Ok(n)) = &res {
            self.counters.written.fetch_add(*n as u64, Ordering::Relaxed);
        }
        res
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_shutdown(cx)
    }
}

/// The byte ranges of the values of the named headers (case-insensitive) in a raw HTTP request: what the prover
/// hides. Only the head (before the blank line) is searched.
pub fn header_value_ranges(request: &[u8], names: &[String]) -> Vec<Range<usize>> {
    let head_end = request.windows(4).position(|w| w == b"\r\n\r\n").unwrap_or(request.len());
    let mut out = Vec::new();
    let mut start = match request.windows(2).position(|w| w == b"\r\n") {
        Some(p) => p + 2, // skip the request line
        None => return out,
    };
    while start < head_end {
        let end = request[start..head_end].windows(2).position(|w| w == b"\r\n").map_or(head_end, |p| start + p);
        let line = &request[start..end];
        if let Some(colon) = line.iter().position(|b| *b == b':') {
            let name = String::from_utf8_lossy(&line[..colon]).trim().to_ascii_lowercase();
            if names.iter().any(|n| n.eq_ignore_ascii_case(&name)) {
                let mut v = start + colon + 1;
                while v < end && request[v] == b' ' {
                    v += 1;
                }
                if v < end {
                    out.push(v..end);
                }
            }
        }
        start = end + 2;
    }
    out
}

/// The complement of `hidden` in 0..len, as sorted ranges: what the prover reveals.
pub fn complement(len: usize, hidden: &[Range<usize>]) -> Vec<Range<usize>> {
    let mut hidden = hidden.to_vec();
    hidden.sort_by_key(|r| r.start);
    let mut out = Vec::new();
    let mut at = 0;
    for r in hidden {
        if r.start > at {
            out.push(at..r.start);
        }
        at = at.max(r.end);
    }
    if at < len {
        out.push(at..len);
    }
    out
}

pub fn ranges_json(ranges: &[Range<usize>]) -> serde_json::Value {
    serde_json::Value::Array(ranges.iter().map(|r| serde_json::json!([r.start, r.end])).collect())
}
