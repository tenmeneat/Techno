export function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  const paths: Record<string, string> = {
    home: "M3 10 12 3l9 7M5 9v12h14V9M9 21v-7h6v7",
    chart: "M4 3v17h17M8 15l4-5 4 3 5-7",
    report: "M6 3h8l5 5v13H6zM14 3v6h5M9 13h7M9 17h5",
    settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
    drop: "M12 3C9 7 5 11 5 15a7 7 0 0 0 14 0c0-4-4-8-7-12zM8 15a4 4 0 0 0 4 4",
    temp: "M9 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0zM12 8v9",
    wall: "M3 4h18v16H3zM3 9h18M3 15h18M10 4v5M16 9v6M9 15v5",
    shield: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6zM8 12l3 3 5-6",
    arrow: "M5 12h14M14 7l5 5-5 5",
    bell: "M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 21h4",
    refresh: "M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3",
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true"><path d={paths[name] ?? paths.home} /></svg>;
}
