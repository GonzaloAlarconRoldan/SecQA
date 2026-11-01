import { lazy } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Empty } from "./components/ui";

// Route-level code splitting keeps the first load small; charts load with the pages that use them.
const CompliancePage = lazy(() => import("./pages/Compliance"));
const DefectDetailPage = lazy(() => import("./pages/DefectDetail"));
const DefectsPage = lazy(() => import("./pages/Defects"));
const FindingsPage = lazy(() => import("./pages/Findings"));
const OverviewPage = lazy(() => import("./pages/Overview"));
const PerformancePage = lazy(() => import("./pages/Performance"));
const ProjectsPage = lazy(() => import("./pages/Projects"));
const ReportsPage = lazy(() => import("./pages/Reports"));
const RunDetailPage = lazy(() => import("./pages/RunDetail"));
const RunsPage = lazy(() => import("./pages/Runs"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const TestCasesPage = lazy(() => import("./pages/TestCases"));

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:id" element={<RunDetailPage />} />
        <Route path="findings" element={<FindingsPage />} />
        <Route path="defects" element={<DefectsPage />} />
        <Route path="defects/:id" element={<DefectDetailPage />} />
        <Route path="testcases" element={<TestCasesPage />} />
        <Route path="performance" element={<PerformancePage />} />
        <Route path="compliance" element={<CompliancePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="*"
          element={
            <Empty message="404">
              <Link className="btn" to="/">
                Home
              </Link>
            </Empty>
          }
        />
      </Route>
    </Routes>
  );
}
