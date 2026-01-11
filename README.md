# TrashMail OPAQUE Authentication Client

A working TypeScript client for TrashMail.com using the OPAQUE protocol (Zero-Knowledge authentication).

## The Problem with Python `opaque`

The Python `opaque` package (libopaque) is **NOT compatible** with TrashMail's OPAQUE implementation:

| Library | Implementation | Compatible |
|---------|---------------|------------|
| `@serenity-kit/opaque` | opaque-ke (Rust/WASM) | ✅ Yes |
| `libopaque` (Python) | libsodium (C) | ❌ No |

The `context` parameter was not the issue - these are completely different OPAQUE implementations with incompatible wire formats.

## Solution: Use TypeScript/JavaScript

This repository provides a working TypeScript implementation using `@serenity-kit/opaque`.

## Installation

```bash
npm install
```

## Usage

### Set environment variables

```bash
export TRASHMAIL_USER="your@email.com"
export TRASHMAIL_PASS="your_password"

# Or for PAT authentication:
export TRASHMAIL_PASS="tmpat_xxxxxx..."
```

### Run

```bash
npm start
```

Or with ts-node directly:

```bash
npx ts-node trashmail-opaque-client.ts
```

## How It Works

### OPAQUE Login Flow

```typescript
import * as opaque from "@serenity-kit/opaque";

// Wait for WASM initialization
await opaque.ready;

// Step 1: Create credential request (KE1)
const { clientLoginState, startLoginRequest } = opaque.client.startLogin({
  password: "your_password",
});

// Step 2: Send to server, get KE2
const response = await fetch("https://trashmail.com/?api=1&cmd=opaque_login_init", {
  method: "POST",
  body: JSON.stringify({ username, startLoginRequest }),
});
const { session_id, loginResponse } = await response.json();

// Step 3: Process KE2, create KE3
const result = opaque.client.finishLogin({
  clientLoginState,
  loginResponse,
  password: "your_password",
});

// Step 4: Send KE3 to server for verification
await fetch("https://trashmail.com/?api=1&cmd=opaque_login_finish", {
  method: "POST",
  body: JSON.stringify({ session_id, finishLoginRequest: result.finishLoginRequest }),
});
```

### PAT-OPAQUE Authentication

Personal Access Tokens use the same OPAQUE flow but with different endpoints:

- `pat_opaque_auth_init` instead of `opaque_login_init`
- `pat_opaque_auth_finish` instead of `opaque_login_finish`
- The PAT token (`tmpat_xxx...`) is used as the password

## For Python Users

If you must use Python, your options are:

1. **Call this TypeScript code via subprocess**
2. **Load the WASM module** using `wasmer` or `wasmtime`
3. **Create PyO3 bindings** for the Rust `opaque-ke` library

The Python `opaque` (libopaque) package will **never work** with TrashMail because it's a different implementation.

## API Reference

| Function | Description |
|----------|-------------|
| `opaqueLogin(username, password)` | OPAQUE login for regular passwords |
| `patOpaqueLogin(username, patToken)` | OPAQUE login for Personal Access Tokens |
| `opaqueRegister(username, password)` | Register OPAQUE credentials |
| `checkAuthMethods(username)` | Check if OPAQUE is enabled for user |

## License

See LICENSE file.
