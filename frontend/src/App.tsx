import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAccess } from "./auth";
import Placeholder from "./components/Placeholder";
import GroupShell from "./pages/GroupShell";
import Groups from "./pages/Groups";
import Join from "./pages/Join";
import Login from "./pages/Login";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <div className="mx-auto min-h-dvh w-full max-w-[480px] bg-white text-slate-900">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/join/:token" element={<Join />} />
        <Route element={<RequireAccess />}>
          <Route path="/groups" element={<Groups />} />
          <Route path="/g/:id" element={<GroupShell />}>
            <Route index element={<Navigate to="expenses" replace />} />
            <Route path="expenses" element={<Placeholder title="Expenses" ticket="012" />} />
            <Route path="balances" element={<Placeholder title="Balances" ticket="013" />} />
            <Route path="recurring" element={<Placeholder title="Recurring" ticket="014" />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/groups" replace />} />
      </Routes>
    </div>
  );
}
