use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

pub struct LocklessRingBuffer {
    capacity: usize,
    buffer: Vec<String>,
    write_head: AtomicUsize,
}

impl LocklessRingBuffer {
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            buffer: vec![String::new(); capacity],
            write_head: AtomicUsize::new(0),
        }
    }

    pub fn push(&mut self, item: String) {
        let idx = self.write_head.fetch_add(1, Ordering::SeqCst) % self.capacity;
        self.buffer[idx] = item;
    }

    pub fn recent(&self, count: usize) -> Vec<String> {
        let head = self.write_head.load(Ordering::SeqCst);
        let actual_count = count.min(self.capacity);
        let mut result = Vec::with_capacity(actual_count);
        for i in 0..actual_count {
            let idx = (head + self.capacity - actual_count + i) % self.capacity;
            let val = &self.buffer[idx];
            if !val.is_empty() {
                result.push(val.clone());
            }
        }
        result
    }
}
