//! Ripper Universal Bypasser Rust Acceleration Core.
//! Exposes native fast AES decryption, regex token extraction, and container unpacking.

pub mod aes_cnl;

pub use aes_cnl::{decrypt_cnl2, extract_key};

#[cfg(feature = "python-bindings")]
use pyo3::prelude::*;

#[cfg(feature = "python-bindings")]
#[pyfunction]
fn py_decrypt_cnl2(crypted: String, jk: String) -> PyResult<Vec<String>> {
    decrypt_cnl2(&crypted, &jk)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))
}

#[cfg(feature = "python-bindings")]
#[pymodule]
fn rust_bypasser(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_decrypt_cnl2, m)?)?;
    Ok(())
}
