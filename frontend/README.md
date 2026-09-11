# Frontend — M0

Approved UI foundation:

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- TanStack Router
- TanStack Query
- TanStack Table

M0 intentionally does **not** build the final rector dashboard.

The first UI after the backend isolation gate should be a minimal authenticated shell showing:

- active institution
- current user
- current roles
- one RLS-protected resource (`campuses`)

Only after the M0 gate is green should definitive role-based dashboard work begin.

UI pattern reference (MIT): `satnaing/shadcn-admin`.
