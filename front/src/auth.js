// Inicio de sesión con Amazon Cognito (hosted UI, código de autorización + PKCE), sin librerías.
// Se activa solo si existen VITE_COGNITO_DOMINIO (p. ej. "hlf-ambulatorio.auth.us-east-1.amazoncognito.com") y
// VITE_COGNITO_CLIENTE (id del cliente web, sin secreto). Opcional: VITE_COGNITO_REDIRECCION (por defecto el origen de
// la página + "/"; debe estar registrada en el cliente de Cognito como URL de retorno y de cierre de sesión).
// Sin esas variables (demo con datos sintéticos) no hay inicio de sesión y todo sigue como antes.
//
// Los tokens viven en sessionStorage (se borran al cerrar la pestaña) y en memoria. Se envía el token de identidad
// (id_token): trae el nombre, el correo y los grupos (roles); API Gateway valida su firma, emisor, audiencia y
// vencimiento antes de llegar a la Lambda. Aquí NO se valida nada: decodificar el token es solo para mostrar el nombre.

const DOMINIO = (import.meta.env.VITE_COGNITO_DOMINIO || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
const CLIENTE = import.meta.env.VITE_COGNITO_CLIENTE || "";
export const activo = Boolean(DOMINIO && CLIENTE);

const CLAVE = "hlf_sesion";
const CLAVE_PKCE = "hlf_pkce";
const MARGEN_MS = 60_000; // renovar un minuto antes de que venza
const redireccion = () => import.meta.env.VITE_COGNITO_REDIRECCION || `${window.location.origin}/`;

let sesion = null;
try { sesion = JSON.parse(sessionStorage.getItem(CLAVE) || "null"); } catch { sesion = null; }

function guardar(s) {
  sesion = s;
  try {
    if (s) sessionStorage.setItem(CLAVE, JSON.stringify(s));
    else sessionStorage.removeItem(CLAVE);
  } catch { /* sin almacenamiento: queda en memoria */ }
}

const base64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const aleatorio = (n) => base64url(crypto.getRandomValues(new Uint8Array(n)));

function afirmaciones(jwt) {
  try {
    const p = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(decodeURIComponent(escape(atob(p + "=".repeat((4 - (p.length % 4)) % 4)))));
  } catch { return {}; }
}

async function pedirTokens(parametros) {
  const r = await fetch(`https://${DOMINIO}/oauth2/token`, {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: CLIENTE, ...parametros }),
  });
  const t = await r.json().catch(() => ({}));
  if (!r.ok || !t.id_token) throw new Error(t.error_description || t.error || `Cognito respondió ${r.status}`);
  return t;
}

function deTokens(t, refrescoAnterior) {
  const exp = afirmaciones(t.id_token).exp;
  return { id_token: t.id_token, access_token: t.access_token, refresh_token: t.refresh_token || refrescoAnterior || null,
    expira: exp ? exp * 1000 : Date.now() + (t.expires_in || 3600) * 1000 };
}

// Lleva a la página de inicio de sesión de Cognito. No vuelve: el navegador cambia de página.
export async function iniciarSesion() {
  const verificador = aleatorio(64);
  const desafio = base64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verificador)));
  const estado = aleatorio(24);
  try { sessionStorage.setItem(CLAVE_PKCE, JSON.stringify({ verificador, estado, volver: window.location.pathname + window.location.search })); } catch { /* */ }
  const q = new URLSearchParams({ response_type: "code", client_id: CLIENTE, redirect_uri: redireccion(), scope: "openid email profile",
    state: estado, code_challenge: desafio, code_challenge_method: "S256" });
  window.location.assign(`https://${DOMINIO}/oauth2/authorize?${q}`);
  return new Promise(() => {}); // la página se va
}

// Al volver de Cognito (?code=…&state=…): canjea el código por los tokens y limpia la URL.
async function completarRetorno() {
  if (!activo) return;
  const url = new URL(window.location.href);
  const code = url.searchParams.get("code"), state = url.searchParams.get("state"), error = url.searchParams.get("error");
  if (!code && !error) return;
  let pkce = {};
  try { pkce = JSON.parse(sessionStorage.getItem(CLAVE_PKCE) || "{}"); sessionStorage.removeItem(CLAVE_PKCE); } catch { /* */ }
  window.history.replaceState(null, "", pkce.volver || url.pathname);
  if (error) throw new Error(`Inicio de sesión rechazado: ${url.searchParams.get("error_description") || error}`);
  if (!pkce.estado || pkce.estado !== state) throw new Error("La respuesta del inicio de sesión no corresponde a esta pestaña. Vuelva a intentar.");
  guardar(deTokens(await pedirTokens({ grant_type: "authorization_code", code, redirect_uri: redireccion(), code_verifier: pkce.verificador })));
}
const listo = completarRetorno();
listo.catch(() => {}); // el error lo ve quien pida un token, no la consola al cargar

async function renovar() {
  if (!sesion?.refresh_token) return false;
  try {
    guardar(deTokens(await pedirTokens({ grant_type: "refresh_token", refresh_token: sesion.refresh_token }), sesion.refresh_token));
    return true;
  } catch { guardar(null); return false; }
}

// Token para la cabecera Authorization, renovado si está por vencer; sin sesión, lleva al inicio de sesión.
// Con la autenticación desactivada (demo) devuelve null.
export async function token() {
  if (!activo) return null;
  await listo;
  if (sesion && sesion.expira - Date.now() > MARGEN_MS) return sesion.id_token;
  if (await renovar()) return sesion.id_token;
  return iniciarSesion();
}

// La API respondió 401 (token vencido o revocado): se intenta renovar una vez; si no, de vuelta al inicio de sesión.
export async function noAutorizado() {
  if (!activo) return false;
  if (await renovar()) return true;
  guardar(null);
  await iniciarSesion();
  return false;
}

// Quién está conectado según el token (solo para mostrar; los permisos reales los da la API en GET /yo).
export function usuarioSesion() {
  if (!activo || !sesion) return null;
  const c = afirmaciones(sesion.id_token);
  return { nombre: c.name || c.email || c["cognito:username"] || null, correo: c.email || null, grupos: c["cognito:groups"] || [] };
}

export function cerrarSesion() {
  guardar(null);
  if (!activo) return;
  const q = new URLSearchParams({ client_id: CLIENTE, logout_uri: redireccion() });
  window.location.assign(`https://${DOMINIO}/logout?${q}`);
}
