# TrashMail Python API Client

A Python client for the TrashMail.com API with authentication support.

## The OPAQUE Compatibility Problem

### Why the original code failed

The original `failing_opaque_code.py` uses the Python `opaque` package (libopaque), which is **NOT compatible** with TrashMail's OPAQUE implementation.

| Library | Implementation | Base | Wire Format |
|---------|---------------|------|-------------|
| `@serenity-kit/opaque` (TrashMail) | JavaScript/WASM | opaque-ke (Rust) | Custom base64url |
| `libopaque` (Python) | C + Python bindings | libsodium | Different format |

These are completely different implementations of the OPAQUE protocol with incompatible wire formats. The `context` parameter was not the issue - the libraries simply cannot interoperate.

### Solution

This repository provides a working Python client that uses the **classic login endpoint**, which:

1. Works immediately without any OPAQUE complexity
2. Is simple and reliable for API automation
3. Automatically migrates accounts to OPAQUE on the server side

## Installation

```bash
pip install requests
```

## Usage

### Basic Login

```python
from trashmail_api import TrashMailClient

client = TrashMailClient()

# Login
if client.login("your@email.com", "your_password"):
    # Get DEAs
    deas = client.get_deas()
    for dea in deas:
        print(dea['dea'])

    # Create a new DEA
    new_dea = client.create_dea("forward-to@example.com")
    print(f"Created: {new_dea['dea']}")

    # Logout
    client.logout()
```

### Using Environment Variables

```bash
export TRASHMAIL_USER="your@email.com"
export TRASHMAIL_PASS="your_password"
python trashmail_api.py
```

### Personal Access Tokens (PAT)

PAT authentication via OPAQUE is currently not supported in Python due to library incompatibility. Use the classic login instead:

```python
client = TrashMailClient()
client.login("your@email.com", "your_password")
```

## Advanced: True OPAQUE in Python

If you absolutely need OPAQUE authentication in Python, here are your options:

### Option 1: WASM Runtime (Recommended for OPAQUE)

Load the @serenity-kit/opaque WASM module using `wasmer` or `wasmtime`:

```python
# pip install wasmer wasmer-compiler-cranelift
import wasmer

# Load the WASM module
wasm_bytes = open("path/to/opaque.wasm", "rb").read()
store = wasmer.Store()
module = wasmer.Module(store, wasm_bytes)
instance = wasmer.Instance(module)

# Call OPAQUE functions
# (Requires understanding of the WASM interface)
```

### Option 2: Node.js Subprocess

If Node.js is available:

```python
import subprocess
import json

def opaque_start_login(password):
    code = f"""
    const opaque = require('@serenity-kit/opaque');
    (async () => {{
        await opaque.ready;
        const result = opaque.client.startLogin({{ password: '{password}' }});
        console.log(JSON.stringify(result));
    }})();
    """
    result = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    return json.loads(result.stdout)
```

### Option 3: PyO3 Bindings for opaque-ke

Create native Python bindings for the Rust `opaque-ke` library using PyO3. This would require:

1. Rust toolchain
2. Understanding of opaque-ke internals
3. Custom compilation

## API Reference

### TrashMailClient

```python
client = TrashMailClient(base_url="https://trashmail.com", lang="en")
```

#### Methods

- `login(username, password)` - Authenticate with classic login
- `logout()` - End session
- `api_call(cmd, **params)` - Make authenticated API call
- `get_deas()` - List all Disposable Email Addresses
- `create_dea(real_email, **options)` - Create new DEA
- `check_auth_methods(username)` - Check available auth methods

#### Properties

- `is_authenticated` - Check if logged in
- `username` - Current username

## Error Handling

```python
from trashmail_api import TrashMailClient, TrashMailAPIError

client = TrashMailClient()

try:
    client.login("user@example.com", "wrong_password")
except TrashMailAPIError as e:
    print(f"Error: {e}")
    print(f"Error code: {e.error_code}")  # e.g., 3 for invalid credentials
```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Submit a pull request

## License

See LICENSE file.
