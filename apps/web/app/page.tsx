const foundation = [
  "Multi-tenant FastAPI foundation",
  "PostgreSQL and Redis services",
  "Celery worker and scheduler",
  "Responsive Next.js application shell",
];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <p className="eyebrow">FleetPulse Intelligence</p>
        <h1>Keep every vehicle safe, available, and accountable.</h1>
        <p className="lede">
          One operational record for inspections, defects, maintenance, and repair work.
        </p>
        <div className="status">Sprint 1 foundation is ready</div>
      </section>
      <section className="panel" aria-labelledby="foundation-heading">
        <h2 id="foundation-heading">Development foundation</h2>
        <ul>
          {foundation.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
