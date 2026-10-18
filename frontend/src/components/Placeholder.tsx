export default function Placeholder({ title, ticket }: { title: string; ticket: string }) {
  return (
    <section className="p-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-slate-600">Coming in ticket {ticket}.</p>
    </section>
  );
}
