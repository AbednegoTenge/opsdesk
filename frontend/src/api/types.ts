import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["User"];
export type Role = Schemas["RoleEnum"];
export type AuthResponse = Schemas["AuthResponse"];
