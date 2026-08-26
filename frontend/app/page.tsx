export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-aeris-black text-aeris-white">
      <main className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-aeris-teal">
          AERIS
        </h1>
        <p className="text-lg text-aeris-gray max-w-lg">
          Agentic Earth Reasoning & Intelligence System
        </p>
        <div className="mt-8 px-4 py-2 border border-aeris-obsidian bg-aeris-obsidian/50 rounded-md shadow-lg backdrop-blur-md">
          <p className="font-mono text-sm text-aeris-blue animate-pulse">
            &gt; Initializing Mission Command Center...
          </p>
        </div>
      </main>
    </div>
  );
}
