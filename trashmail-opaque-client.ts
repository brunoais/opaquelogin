/**
 * TrashMail OPAQUE Authentication Client
 *
 * This is a working implementation using @serenity-kit/opaque,
 * which is compatible with TrashMail's server.
 *
 * Usage:
 *   npx ts-node trashmail-opaque-client.ts
 *
 * Or compile and run:
 *   npx tsc trashmail-opaque-client.ts
 *   node trashmail-opaque-client.js
 *
 * @author TrashMail Team (Aionda GmbH)
 */

import * as opaque from "@serenity-kit/opaque";

const API_BASE_URL = process.env.TRASHMAIL_API_URL || "https://trashmail.com";

interface ApiResponse {
  success: boolean;
  error_code?: number;
  msg?: string;
  session_id?: string;
  loginResponse?: string;
  login_response?: string;
  data?: Record<string, unknown>;
}

/**
 * Make an API request to TrashMail
 */
async function apiRequest(
  cmd: string,
  body: Record<string, unknown>
): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/?api=1&cmd=${cmd}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

/**
 * Check available authentication methods for a user
 */
async function checkAuthMethods(
  username: string
): Promise<{ opaque_enabled: boolean; srp_enabled: boolean }> {
  const result = await apiRequest("opaque_check", { username });
  return {
    opaque_enabled: result.data?.opaque_enabled as boolean ?? false,
    srp_enabled: result.data?.srp_enabled as boolean ?? false,
  };
}

/**
 * Login with OPAQUE (Zero-Knowledge authentication)
 *
 * This is the recommended way to authenticate with TrashMail.
 * The password never leaves the client - only cryptographic proofs are sent.
 */
async function opaqueLogin(
  username: string,
  password: string
): Promise<{ success: boolean; sessionKey?: Uint8Array; error?: string }> {
  // CRITICAL: Wait for WASM to initialize
  await opaque.ready;

  // Step 1: Start login - create KE1
  const { clientLoginState, startLoginRequest } = opaque.client.startLogin({
    password,
  });

  const step1Result = await apiRequest("opaque_login_init", {
    username,
    startLoginRequest, // Already base64url encoded by the library
  });

  if (!step1Result.success || !step1Result.session_id) {
    return {
      success: false,
      error: step1Result.msg || "OPAQUE login init failed",
    };
  }

  // Step 2: Finish login - process KE2, create KE3
  const loginResponse =
    step1Result.loginResponse || step1Result.login_response || "";

  const loginResult = opaque.client.finishLogin({
    clientLoginState,
    loginResponse,
    password,
  });

  // finishLogin returns null/undefined if password is incorrect
  if (!loginResult || !loginResult.finishLoginRequest) {
    return { success: false, error: "Incorrect password" };
  }

  // Step 3: Send KE3 to server for verification
  const step2Result = await apiRequest("opaque_login_finish", {
    session_id: step1Result.session_id,
    finishLoginRequest: loginResult.finishLoginRequest,
  });

  if (!step2Result.success) {
    return {
      success: false,
      error: step2Result.msg || "OPAQUE verification failed",
    };
  }

  return {
    success: true,
    sessionKey: loginResult.sessionKey,
  };
}

/**
 * Login with Personal Access Token (PAT) via OPAQUE
 *
 * PATs use a separate OPAQUE verifier stored in mail_opaque_access_tokens.
 * The token (starting with 'tmpat_') is used as the password.
 */
async function patOpaqueLogin(
  username: string,
  patToken: string
): Promise<{ success: boolean; sessionKey?: Uint8Array; error?: string }> {
  if (!patToken.startsWith("tmpat_")) {
    return { success: false, error: "Invalid PAT format. Must start with 'tmpat_'" };
  }

  // CRITICAL: Wait for WASM to initialize
  await opaque.ready;

  // Step 1: Start PAT-OPAQUE login - create KE1
  const { clientLoginState, startLoginRequest } = opaque.client.startLogin({
    password: patToken, // PAT is used as the password
  });

  const step1Result = await apiRequest("pat_opaque_auth_init", {
    username,
    token_prefix: `${patToken.substring(0, 12)}...`,
    startLoginRequest,
  });

  if (!step1Result.success || !step1Result.session_id) {
    return {
      success: false,
      error: step1Result.msg || "PAT authentication init failed",
    };
  }

  // Step 2: Finish login - process KE2, create KE3
  const loginResponse =
    step1Result.loginResponse || step1Result.login_response || "";

  const loginResult = opaque.client.finishLogin({
    clientLoginState,
    loginResponse,
    password: patToken,
  });

  if (!loginResult || !loginResult.finishLoginRequest) {
    return { success: false, error: "Invalid Personal Access Token" };
  }

  // Step 3: Send KE3 proof to server
  const step2Result = await apiRequest("pat_opaque_auth_finish", {
    session_id: step1Result.session_id,
    finishLoginRequest: loginResult.finishLoginRequest,
  });

  if (!step2Result.success) {
    return {
      success: false,
      error: step2Result.msg || "PAT verification failed",
    };
  }

  return {
    success: true,
    sessionKey: loginResult.sessionKey,
  };
}

/**
 * Register OPAQUE credentials for an account
 *
 * Call this after classic login to migrate to OPAQUE,
 * or during account registration.
 */
async function opaqueRegister(
  username: string,
  password: string
): Promise<{ success: boolean; error?: string }> {
  await opaque.ready;

  // Step 1: Start registration
  const { clientRegistrationState, registrationRequest } =
    opaque.client.startRegistration({ password });

  const step1Result = await apiRequest("opaque_register_init", {
    username,
    registrationRequest,
  });

  if (!step1Result.success || !step1Result.session_id) {
    return {
      success: false,
      error: step1Result.msg || "Registration init failed",
    };
  }

  // Step 2: Finish registration
  const registrationResponse =
    (step1Result.data?.registrationResponse as string) ||
    (step1Result.data?.registration_response as string) ||
    "";

  const { registrationRecord } = opaque.client.finishRegistration({
    clientRegistrationState,
    registrationResponse,
    password,
  });

  const step2Result = await apiRequest("opaque_register_finish", {
    session_id: step1Result.session_id,
    registrationRecord,
  });

  return {
    success: step2Result.success,
    error: step2Result.msg,
  };
}

// =============================================================================
// Example Usage
// =============================================================================

async function main() {
  const username = process.env.TRASHMAIL_USER || "";
  const password = process.env.TRASHMAIL_PASS || "";

  if (!username || !password) {
    console.log("Set TRASHMAIL_USER and TRASHMAIL_PASS environment variables");
    console.log("Example:");
    console.log('  export TRASHMAIL_USER="your@email.com"');
    console.log('  export TRASHMAIL_PASS="your_password"');
    console.log('  # Or for PAT:');
    console.log('  export TRASHMAIL_PASS="tmpat_xxxxxx..."');
    process.exit(1);
  }

  console.log(`Checking auth methods for ${username}...`);
  const authMethods = await checkAuthMethods(username);
  console.log("Auth methods:", authMethods);

  // Determine if password is a PAT
  const isPAT = password.startsWith("tmpat_");

  let result;
  if (isPAT) {
    console.log("Authenticating with PAT-OPAQUE...");
    result = await patOpaqueLogin(username, password);
  } else if (authMethods.opaque_enabled) {
    console.log("Authenticating with OPAQUE...");
    result = await opaqueLogin(username, password);
  } else {
    console.log("OPAQUE not enabled for this user.");
    console.log("Use classic login first, then the account will be migrated to OPAQUE.");
    process.exit(1);
  }

  if (result.success) {
    console.log("✅ Authentication successful!");
    console.log("Session key (first 16 bytes):",
      Buffer.from(result.sessionKey!.slice(0, 16)).toString("hex"));
  } else {
    console.log("❌ Authentication failed:", result.error);
    process.exit(1);
  }
}

main().catch(console.error);
