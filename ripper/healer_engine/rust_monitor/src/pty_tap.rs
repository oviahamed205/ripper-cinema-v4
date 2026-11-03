use std::io::{BufRead, BufReader, Read};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use crossbeam_channel::{unbounded, Receiver, Sender};

pub struct PtyTap {
    is_running: Arc<AtomicBool>,
    sender: Sender<String>,
    receiver: Receiver<String>,
}

impl PtyTap {
    pub fn new() -> Self {
        let (sender, receiver) = unbounded();
        Self {
            is_running: Arc::new(AtomicBool::new(false)),
            sender,
            receiver,
        }
    }

    pub fn attach_reader<R: Read + Send + 'static>(&self, reader: R) {
        self.is_running.store(true, Ordering::SeqCst);
        let sender = self.sender.clone();
        let running = Arc::clone(&self.is_running);

        thread::spawn(move || {
            let buf = BufReader::new(reader);
            for line_res in buf.lines() {
                if !running.load(Ordering::SeqCst) {
                    break;
                }
                if let Ok(line) = line_res {
                    let _ = sender.send(line);
                }
            }
        });
    }

    pub fn poll_events(&self) -> Vec<String> {
        let mut events = Vec::new();
        while let Ok(msg) = self.receiver.try_recv() {
            events.push(msg);
        }
        events
    }

    pub fn stop(&self) {
        self.is_running.store(false, Ordering::SeqCst);
    }
}
