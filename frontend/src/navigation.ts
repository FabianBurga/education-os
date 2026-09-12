import type { UiBootstrap } from "./types/bootstrap";

export interface ModuleDefinition {
  id: string;
  label: string;
  shortLabel: string;
  description: string;
  permission: string;
  legacyPath: string;
  capabilityKey?: string;
  audience: string;
}

export const MODULES: ModuleDefinition[] = [
  {
    id: "administration",
    label: "Administración",
    shortLabel: "Admin",
    description:
      "Configuración institucional, personas, accesos, estructura académica y matrícula.",
    permission: "admin.console.access",
    legacyPath: "/api/v1/admin/dashboard",
    audience: "Administración",
  },
  {
    id: "coordination",
    label: "Rectorado y coordinación",
    shortLabel: "Rectorado",
    description:
      "Visión ejecutiva, señales, seguimiento y coordinación académica.",
    permission: "coord.console.access",
    legacyPath: "/api/v1/coordination/dashboard",
    audience: "Rectorado",
  },
  {
    id: "teacher",
    label: "Docentes",
    shortLabel: "Docentes",
    description:
      "Clases, asistencia, calificaciones y tareas dentro del alcance docente.",
    permission: "teacher.console.access",
    legacyPath: "/api/v1/teacher/dashboard",
    audience: "Docentes",
  },
  {
    id: "student",
    label: "Estudiantes",
    shortLabel: "Estudiantes",
    description:
      "Clases, horario, asistencia, calificaciones, progreso y avisos del estudiante.",
    permission: "student.console.access",
    legacyPath: "/api/v1/student/dashboard",
    audience: "Estudiante",
  },
  {
    id: "guardian",
    label: "Familias",
    shortLabel: "Familias",
    description:
      "Información permitida para representantes y seguimiento de sus estudiantes.",
    permission: "guardian.console.access",
    legacyPath: "/api/v1/guardian/dashboard",
    audience: "Familia",
  },
  {
    id: "communications",
    label: "Comunicaciones",
    shortLabel: "Comunicaciones",
    description:
      "Mensajes institucionales, segmentación, publicación y seguimiento de entrega.",
    permission: "communications.console.access",
    legacyPath: "/api/v1/communications/dashboard",
    audience: "Gestión",
  },
  {
    id: "finance",
    label: "Finanzas",
    shortLabel: "Finanzas",
    description:
      "Conceptos, obligaciones, pagos, saldos y estados de cuenta institucionales.",
    permission: "finance.console.access",
    legacyPath: "/api/v1/finance/dashboard",
    capabilityKey: "finance.billing",
    audience: "Finanzas",
  },
];

export function modulesForContext(
  bootstrap: UiBootstrap,
): ModuleDefinition[] {
  const permissions = new Set(bootstrap.permissions);
  return MODULES.filter((module) => permissions.has(module.permission));
}

export function moduleCapabilityState(
  module: ModuleDefinition,
  bootstrap: UiBootstrap,
): "enabled" | "disabled" | "not-applicable" {
  if (!module.capabilityKey) {
    return "not-applicable";
  }
  return bootstrap.capabilities[module.capabilityKey] === true
    ? "enabled"
    : "disabled";
}

export function findModule(
  moduleId: string,
): ModuleDefinition | undefined {
  return MODULES.find((module) => module.id === moduleId);
}
