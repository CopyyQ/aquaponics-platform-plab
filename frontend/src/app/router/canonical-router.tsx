import { lazy, Suspense, type ComponentType, type ReactNode } from "react"
import { Navigate, Outlet, createBrowserRouter, RouterProvider, useLocation } from "react-router-dom"
import { AppShell } from "@/app/layouts/app-shell"
import { AquaponicsSystemLayout } from "@/app/layouts/aquaponics-system-layout"
import { OperatorConsoleLayout, OperatorSystemFrame } from "@/app/layouts/operator-console-layout"
import { OwnerConsoleLayout } from "@/app/layouts/owner-console-layout"
import { isOperatorConsole, mustStayOnPasswordChange, readAccountRole } from "@/app/lib/operator-console"
import { useAuth } from "@/app/auth"
import { Skeleton } from "@/shared/ui/skeleton"
import { EmptyState } from "@/shared/ui/empty-state"
import { ShieldAlert } from "lucide-react"

function lazyNamed<T extends Record<K, ComponentType>, K extends keyof T>(loader: () => Promise<T>, name: K) {
  return lazy(async () => ({ default: (await loader())[name] }))
}

const LoginPage = lazyNamed(() => import("@/pages/login"), "LoginPage")
const SystemsPage = lazyNamed(() => import("@/pages/systems-canonical"), "SystemsPage")
const OperatorHomePage = lazyNamed(() => import("@/pages/operator-home/OperatorHomePage"), "OperatorHomePage")
const OverviewPage = lazyNamed(() => import("@/pages/overview"), "OverviewPage")
const OperatorOverviewPage = lazyNamed(() => import("@/pages/operator-overview/OperatorOverviewPage"), "OperatorOverviewPage")
const OwnerOverviewPage = lazyNamed(() => import("@/pages/owner-overview/OwnerOverviewPage"), "OwnerOverviewPage")
const ScadaPage = lazyNamed(() => import("@/pages/scada"), "ScadaPage")
const MonitoringPage = lazyNamed(() => import("@/pages/monitoring"), "MonitoringPage")
const DevicesPage = lazyNamed(() => import("@/pages/devices-canonical"), "DevicesPage")
const OperatorDevicesPage = lazyNamed(() => import("@/pages/operator-devices/OperatorDevicesPage"), "OperatorDevicesPage")
const DeviceDetailPage = lazyNamed(() => import("@/pages/device-detail-activation"), "DeviceDetailCanonicalPage")
const ProjectScenarioDetailPage = lazyNamed(() => import("@/pages/project-scenario-detail"), "ProjectScenarioDetailPage")
const SensorDetailPage = lazyNamed(() => import("@/pages/sensor-detail-canonical"), "SensorDetailPage")
const ActuatorDetailPage = lazyNamed(() => import("@/pages/actuator-detail-canonical"), "ActuatorDetailPage")
const AlertsPage = lazyNamed(() => import("@/pages/alerts-activation"), "AlertsPage")
const OperatorAlertsPage = lazyNamed(() => import("@/pages/operator-alerts/OperatorAlertsPage"), "OperatorAlertsPage")
const AlertDetailPage = lazyNamed(() => import("@/pages/alert-detail-canonical"), "AlertDetailPage")
const MembersPage = lazyNamed(() => import("@/pages/members"), "MembersPage")
const ActivitiesPage = lazyNamed(() => import("@/pages/activities"), "ActivitiesPage")
const SettingsPage = lazyNamed(() => import("@/pages/settings-canonical"), "SettingsPage")
const OperatorSettingsPage = lazyNamed(() => import("@/pages/operator-settings/OperatorSettingsPage"), "OperatorSettingsPage")
const AlertDeliveryPage = lazyNamed(() => import("@/pages/alert-delivery"), "AlertDeliveryPage")
const CatalogsPage = lazyNamed(() => import("@/pages/catalog-hub"), "CatalogHubPage")
const UsersPage = lazyNamed(() => import("@/pages/users-canonical"), "UsersPage")
const UserDetailPage = lazyNamed(() => import("@/pages/user-detail-canonical"), "UserDetailPage")
const ProfilePage = lazyNamed(() => import("@/pages/profile-canonical"), "ProfilePage")
const NotFoundPage = lazyNamed(() => import("@/pages/not-found-canonical"), "NotFoundCanonicalPage")

function PageSuspense({ children }: { children: ReactNode }) {
  return <Suspense fallback={<div className="space-y-4"><Skeleton className="h-20" /><Skeleton className="h-72" /></div>}>{children}</Suspense>
}

function Guard() {
  const { session, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="p-8"><Skeleton className="h-10 w-48" /></div>
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  const operator = isOperatorConsole(session.permissions, readAccountRole())
  if (mustStayOnPasswordChange(session.user.must_change_password, location.pathname, operator)) {
    return <Navigate to="/profile?change-password=required" replace />
  }
  return <Outlet />
}

function LoginRoute() {
  const { session } = useAuth()
  return session ? <Navigate to="/aquaponics-systems" replace /> : <LoginPage />
}

function PermissionGuard({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth()
  return can(permission) ? children : <EmptyState icon={ShieldAlert} title="Không có quyền truy cập" description={`Phiên hiện tại không có quyền ${permission}. Backend vẫn là lớp thực thi bảo mật cuối cùng.`} />
}

function ConsoleShell() {
  const { session } = useAuth()
  const role = readAccountRole()
  if (role === "OWNER") return <OwnerConsoleLayout />
  return isOperatorConsole(session?.permissions, role) ? <OperatorConsoleLayout /> : <AppShell />
}

function SystemsEntry() {
  const { session } = useAuth()
  return isOperatorConsole(session?.permissions, readAccountRole()) ? <OperatorHomePage /> : <SystemsPage />
}

function SystemWorkspace() {
  const { session } = useAuth()
  return isOperatorConsole(session?.permissions, readAccountRole()) ? <OperatorSystemFrame /> : <AquaponicsSystemLayout />
}

function OperatorOrAdmin({ admin, operator, owner }: { admin: ReactNode; operator: ReactNode; owner?: ReactNode }) {
  const { session } = useAuth()
  const role = readAccountRole()
  if (owner && role === "OWNER") return owner
  return isOperatorConsole(session?.permissions, role) ? operator : admin
}

const child = (element: ReactNode) => ({ element: <PageSuspense>{element}</PageSuspense> })
const permitted = (permission: string, element: ReactNode) => child(<PermissionGuard permission={permission}>{element}</PermissionGuard>)

const router = createBrowserRouter([
  { path: "/login", element: <LoginRoute /> },
  { element: <Guard />, children: [{ element: <ConsoleShell />, children: [
    { index: true, element: <Navigate to="/aquaponics-systems" replace /> },
    { path: "/aquaponics-systems", ...permitted("aquaponics_systems.read", <SystemsEntry />) },
    { path: "/aquaponics-systems/:systemId", element: <PermissionGuard permission="aquaponics_systems.read"><SystemWorkspace /></PermissionGuard>, children: [
      { index: true, element: <Navigate to="overview" replace /> },
      { path: "overview", ...permitted("aquaponics_systems.read", <OperatorOrAdmin admin={<OverviewPage />} operator={<OperatorOverviewPage />} owner={<OwnerOverviewPage />} />) },
      { path: "scada", ...permitted("scada.read", <ScadaPage />) },
      { path: "monitoring", ...permitted("monitoring.read", <MonitoringPage />) },
      { path: "devices", ...permitted("devices.read", <OperatorOrAdmin admin={<DevicesPage />} operator={<OperatorDevicesPage />} />) },
      { path: "devices/:deviceId", ...permitted("devices.read", <DeviceDetailPage />) },
      { path: "devices/:deviceId/scenarios/:scenarioId", ...permitted("project_scenarios.read", <ProjectScenarioDetailPage />) },
      { path: "devices/:deviceId/sensors/:sensorId", ...permitted("sensors.read", <SensorDetailPage />) },
      { path: "devices/:deviceId/actuators/:actuatorId", ...permitted("actuators.read", <ActuatorDetailPage />) },
      { path: "alerts", ...permitted("incidents.read", <OperatorOrAdmin admin={<AlertsPage />} operator={<OperatorAlertsPage />} />) },
      { path: "alerts/:alertId", ...permitted("incidents.read", <AlertDetailPage />) },
      { path: "members", ...permitted("aquaponics_systems.read", <MembersPage />) },
      { path: "activities", ...permitted("activities.read", <ActivitiesPage />) },
      { path: "notifications", ...permitted("notifications.settings.read", <AlertDeliveryPage />) },
      { path: "settings", ...permitted("aquaponics_systems.read", <OperatorOrAdmin admin={<SettingsPage />} operator={<OperatorSettingsPage />} />) },
    ] },
    { path: "/catalogs", ...permitted("device_templates.read", <CatalogsPage />) },
    { path: "/users", ...permitted("users.read", <UsersPage />) },
    { path: "/users/:userId", ...permitted("users.read", <UserDetailPage />) },
    { path: "/profile", ...child(<ProfilePage />) },
  ] }] },
  { path: "*", ...child(<NotFoundPage />) },
])

export function AppRouter() { return <RouterProvider router={router} /> }
