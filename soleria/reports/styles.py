"""Folha de estilo embutida nos relatórios e no catálogo.

Mantida em um módulo separado para o renderizador cuidar apenas da
estrutura do documento. O CSS é local e não carrega recursos externos.
"""

CSS = """
:root {
  --bg: #0d0f14;
  --bg2: #12151c;
  --card: #171b24;
  --card2: #1d222d;
  --text: #e8eaf0;
  --muted: #9aa3b5;
  --line: #2a3140;
  --accent: #55f5ee;
  --accent2: #ff55cf;
  --radius: 14px;
  --max: 920px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background:
    radial-gradient(900px 500px at 15% -10%, rgba(85,245,238,.12), transparent 60%),
    radial-gradient(800px 500px at 110% 0%, rgba(255,85,207,.10), transparent 55%),
    var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
  font-size: 16px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap {
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 64px;
}
.voltar {
  display: inline-block;
  margin-bottom: 18px;
  color: var(--muted);
  font-size: .9rem;
}
.voltar:hover { color: var(--accent); }
.capa {
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 28px 30px;
  box-shadow: 0 14px 40px rgba(0,0,0,.22);
}
.marca {
  margin: 0;
  color: var(--accent);
  font-size: .74rem;
  font-weight: 700;
  letter-spacing: .18em;
  text-transform: uppercase;
}
h1 {
  font-size: clamp(1.9rem, 4vw, 2.8rem);
  line-height: 1.15;
  margin: .35rem 0 1rem;
  letter-spacing: -.02em;
}
.resumo {
  font-size: 1.08rem;
  color: #cbd2df;
  max-width: 72ch;
  margin: .5rem 0;
}
.datas, .contagem {
  color: var(--muted);
  font-size: .86rem;
  margin: .25rem 0 0;
}
.sumario {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px 22px;
  margin: 26px 0;
}
.sumario h2 {
  font-size: .78rem;
  text-transform: uppercase;
  letter-spacing: .14em;
  color: var(--muted);
  margin: 0 0 10px;
}
.sumario ol {
  margin: 0;
  padding-left: 1.2rem;
  columns: 2;
  column-gap: 28px;
}
.sumario li { margin: 4px 0; break-inside: avoid; }
.secao {
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius);
  padding: 24px 26px;
  margin: 24px 0;
  box-shadow: 0 10px 30px rgba(0,0,0,.18);
}
.secao h2 {
  margin: 0 0 6px;
  font-size: 1.45rem;
  letter-spacing: -.01em;
}
.secao .meta {
  color: var(--muted);
  font-size: .82rem;
  margin: 0 0 18px;
}
.secao h3 { margin: 1.4rem 0 .5rem; font-size: 1.1rem; color: #f2f5fa; }
.secao h4 { margin: 1.2rem 0 .4rem; font-size: 1rem; color: #dfe5ef; }
.secao h5, .secao h6 {
  margin: 1rem 0 .35rem;
  font-size: .95rem;
  color: #dfe5ef;
}
.secao p { margin: .75rem 0; }
.secao ul, .secao ol { margin: .6rem 0 .9rem; padding-left: 1.4rem; }
.secao li { margin: .3rem 0; }
blockquote {
  margin: 1rem 0;
  padding: .6rem 1rem;
  border-left: 2px solid var(--accent2);
  background: rgba(255,85,207,.06);
  color: #d7dcea;
}
code {
  background: #0b0d12;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .1em .35em;
  font-size: .9em;
}
pre {
  background: #0b0d12;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px;
  overflow-x: auto;
}
pre code { border: 0; padding: 0; background: transparent; }
hr { border: 0; border-top: 1px solid var(--line); margin: 1.6rem 0; }
.citacao {
  font-size: .78em;
  vertical-align: super;
  line-height: 0;
  color: var(--accent2);
  font-weight: 600;
}
.fontes { list-style: none; padding: 0; margin: 0; counter-reset: fonte; }
.fontes li {
  counter-increment: fonte;
  position: relative;
  padding: 12px 14px 12px 48px;
  border: 1px solid var(--line);
  border-radius: 10px;
  margin: 8px 0;
  background: rgba(255,255,255,.02);
}
.fontes li::before {
  content: "[" counter(fonte) "]";
  position: absolute;
  left: 14px;
  top: 12px;
  color: var(--accent);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.fontes .dominio {
  display: block;
  color: var(--muted);
  font-size: .82rem;
  margin-top: 2px;
}
.fontes .acessado {
  display: block;
  color: #6f788a;
  font-size: .75rem;
  margin-top: 2px;
}
.grade {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin: 26px 0;
}
.cartao {
  display: block;
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 20px;
  color: var(--text);
  transition: border-color .15s, transform .15s;
}
.cartao:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
  text-decoration: none;
}
.cartao h2 { margin: 0 0 8px; font-size: 1.15rem; }
.cartao p { margin: 0 0 12px; color: var(--muted); font-size: .92rem; }
.cartao .meta { color: #7e8799; font-size: .78rem; margin: 0; }
.vazio {
  color: var(--muted);
  background: var(--card);
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  padding: 28px;
  text-align: center;
}
footer {
  margin-top: 40px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: .82rem;
}
@media (max-width: 640px) {
  .sumario ol { columns: 1; }
  .secao { padding: 20px 18px; }
  .capa { padding: 22px 20px; }
}
@media print {
  body { background: #fff; color: #111; }
  .voltar { display: none; }
  .capa, .secao, .sumario {
    background: #fff;
    box-shadow: none;
    border-color: #ddd;
  }
  a { color: #0645ad; }
  .secao { break-inside: avoid; }
}
"""
