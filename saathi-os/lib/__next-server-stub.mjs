// Minimal stand-in for `next/server` so the real route module can be imported
// outside a Next runtime. Only the one call the route makes is modelled.
export const NextResponse = {
  json: (body, init = {}) => ({ status: init.status ?? 200, json: async () => body }),
};
