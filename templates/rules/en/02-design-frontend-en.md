# Design System and Frontend Rules

These rules are NON-NEGOTIABLE and must be applied in all frontend interactions and code generation.

## 1. Colors and CSS Variables
- NEVER use hardcoded colors in Tailwind (e.g., `bg-blue-500`, `text-red-600`).
- ALWAYS use the CSS variables defined in the Design System (e.g., `bg-primary`, `text-on-surface`, `bg-action-delete`).
- The color system is multi-tenant and dynamic; using hardcoded colors breaks client customization.

## 2. Tab Routing
- NEVER use local state (`useState`) to control navigation between main tabs of a page.
- ALWAYS use dedicated React Router routes (e.g., `/settings/profile`, `/settings/billing`).
- This ensures the URL is shareable and the browser's "Back" button works correctly.

## 3. Icons
- Use EXCLUSIVELY the Phosphor Icons library.
- Take advantage of the 6 available weights (thin, light, regular, bold, fill, duotone) according to the visual context.

## 4. Base Components
- Use components based on Radix UI or Headless UI for accessibility (a11y).
- Encapsulate complex logic in reusable components (e.g., `PrimaryButton`, `Card`, `Modal`).

## 5. API Calls
- NEVER use `fetch` or `axios` directly in components.
- ALWAYS use the configured `apiClient` instance (which already injects the JWT token and handles 401 errors).
- Use React Query (or SWR) to manage server state, caching, and data revalidation.
