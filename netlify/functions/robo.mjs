export default async () => {
  const token = Netlify.env.get("GITHUB_TOKEN");
  if (!token) { console.error("GITHUB_TOKEN não configurado."); return; }
  const r = await fetch("https://api.github.com/repos/Jefestuart/econoia/actions/workflows/update.yml/dispatches", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "User-Agent": "EconoIA-robo" },
    body: JSON.stringify({ ref: "main" }),
  });
  console.log(r.status === 204 ? "Robô disparado com sucesso." : `Erro HTTP ${r.status}`);
};
export const config = { schedule: "*/15 * * * *" };

