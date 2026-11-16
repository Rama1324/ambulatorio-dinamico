// Qué acciones muestra la pantalla según el rol. En la demo (sin inicio de sesión) el rol se elige arriba y viaja en la
// cabecera X-Rol: es declarativo, la API no lo verifica. Con inicio de sesión (Cognito) los roles vienen del token (GET /yo).
// Jerarquía igual a la de la API (lambda/seguridad.py): gestión < especialista < jefatura.
import { createContext, useContext } from "react";

export const ROLES = ["gestion", "especialista", "jefatura"];
export const ROL_TXT = { gestion: "Gestión de lista", especialista: "Especialista", jefatura: "Jefatura" };

// roles efectivos: los del token si hay sesión real; si no, el rol declarado; sin rol elegido, todos (modo demostración)
export function rolesEfectivos(yo, rolDeclarado) {
  if (yo?.origen === "token") return yo.roles || [];
  return rolDeclarado ? [rolDeclarado] : ROLES;
}
export const crearPuede = (roles) => (nivel) => roles.some((r) => ROLES.indexOf(r) >= ROLES.indexOf(nivel));

export const Permisos = createContext(() => true);
export const usePuede = () => useContext(Permisos);
