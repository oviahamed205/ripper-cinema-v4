pub mod ring_buffer;
pub mod simd_matcher;
pub mod pty_tap;

use ring_buffer::LocklessRingBuffer;
use simd_matcher::ErrorPatternMatcher;
use std::sync::Mutex;
use std::ffi::{CStr, CString};
use std::os::raw::c_char;

static GLOBAL_MATCHER: Mutex<Option<ErrorPatternMatcher>> = Mutex::new(None);

#[no_mangle]
pub extern "C" fn monitor_init() -> i32 {
    let mut matcher = GLOBAL_MATCHER.lock().unwrap();
    *matcher = Some(ErrorPatternMatcher::new());
    0
}

#[no_mangle]
pub extern "C" fn monitor_fast_match(input: *const c_char) -> *mut c_char {
    if input.is_null() {
        return std::ptr::null_mut();
    }
    let c_str = unsafe { CStr::from_ptr(input) };
    let slice = match c_str.to_str() {
        Ok(s) => s,
        Err(_) => return std::ptr::null_mut(),
    };

    let matcher_guard = GLOBAL_MATCHER.lock().unwrap();
    if let Some(ref m) = *matcher_guard {
        if let Some((kind, remedy)) = m.fast_scan(slice) {
            let json = format!("{{\"error_type\":\"{}\",\"remedy\":\"{}\"}}", kind, remedy);
            return CString::new(json).unwrap().into_raw();
        }
    }
    std::ptr::null_mut()
}

#[no_mangle]
pub extern "C" fn monitor_free_string(s: *mut c_char) {
    if !s.is_null() {
        unsafe { let _ = CString::from_raw(s); }
    }
}
