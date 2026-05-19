const API = "/api";
import { useMemo, useState } from "react";

const LINES = [
  { id: "acronis", name: "Acronis" },
  { id: "fortinet", name: "Firewall (Fortinet)" },
  { id: "bare_metal", name: "Bare Metal" },
  { id: "colocation", name: "Colocation" }
];

export default function App() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [line, setLine] = useState("acronis");
  const [catalog, setCatalog] = useState([]);
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState([]);
  const [result, setResult] = useState(null);
  const [months, setMonths] = useState(36);
  const [hours, setHours] = useState(4);
  const [fx, setFx] = useState(1);
  const [settings, setSettings] = useState(null);
  const [loginData, setLoginData] = useState({ username: "admin", password: "admin123" });

  const authHeader = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  async function login() {
    const res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(loginData)
    });
    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Falha no login");
    setToken(data.access_token);
    setRole(data.role);
  }

  async function loadCatalog() {
    const res = await fetch(`${API}/catalog/${line}?q=${encodeURIComponent(search)}`, { headers: authHeader });
    const data = await res.json();
    setCatalog(Array.isArray(data) ? data : []);
  }

  function addItem(item) {
    setCart((prev) => {
      const found = prev.find((x) => x.sku === item.sku);
      if (found) return prev.map((x) => (x.sku === item.sku ? { ...x, quantity: x.quantity + 1 } : x));
      return [...prev, { sku: item.sku, description: item.description, quantity: 1 }];
    });
  }

  async function calculate() {
    const res = await fetch(`${API}/pricing/calculate`, {
      method: "POST",
      headers: { ...authHeader, "Content-Type": "application/json" },
      body: JSON.stringify({
        line,
        customer_name: "Cliente Demo",
        contract_months: Number(months),
        analyst_hours: Number(hours),
        exchange_rate: Number(fx),
        items: cart.map((c) => ({ sku: c.sku, quantity: Number(c.quantity) }))
      })
    });
    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Erro no cálculo");
    setResult(data);
  }

  async function loadSettings() {
    const res = await fetch(`${API}/admin/settings/${line}`, { headers: authHeader });
    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Erro ao carregar config");
    setSettings(data);
  }

  async function saveSettings() {
    const res = await fetch(`${API}/admin/settings/${line}`, {
      method: "PUT",
      headers: { ...authHeader, "Content-Type": "application/json" },
      body: JSON.stringify(settings)
    });
    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Erro ao salvar");
    alert("Configuração salva");
  }

  async function importPriceList(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("line", line);
    form.append("supplier_name", line.toUpperCase());
    form.append("sku_column", "part");
    form.append("desc_column", "desc");
    form.append("cost_column", "price");
    form.append("type_column", "type");
    form.append("currency", line === "fortinet" ? "USD" : "BRL");
    form.append("file", file);

    const res = await fetch(`${API}/admin/import-price-list`, { method: "POST", headers: authHeader, body: form });
    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Falha no import");
    alert(`Importação concluída. ${data.imported} itens.`);
  }

  if (!token) {
    return (
      <div className="page center">
        <div className="card">
          <h1>GOX Pricing Platform</h1>
          <p>Login inicial</p>
          <input placeholder="Usuário" value={loginData.username} onChange={(e) => setLoginData({ ...loginData, username: e.target.value })} />
          <input placeholder="Senha" type="password" value={loginData.password} onChange={(e) => setLoginData({ ...loginData, password: e.target.value })} />
          <button onClick={login}>Entrar</button>
          <small>admin/admin123 ou vendas/vendas123</small>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header>
        <h1>GOX Pricing Platform</h1>
        <div>Perfil: <b>{role}</b></div>
      </header>

      <section className="cards">
        {LINES.map((l) => (
          <button key={l.id} className={line === l.id ? "line active" : "line"} onClick={() => setLine(l.id)}>{l.name}</button>
        ))}
      </section>

      <section className="grid">
        <div className="card">
          <h2>Catálogo</h2>
          <div className="row">
            <input placeholder="Pesquisar SKU/Nome" value={search} onChange={(e) => setSearch(e.target.value)} />
            <button onClick={loadCatalog}>Buscar</button>
          </div>
          <div className="list">
            {catalog.map((i) => (
              <div key={i.sku} className="item">
                <div><b>{i.sku}</b> - {i.description}</div>
                <div>{i.currency} {i.unit_cost}</div>
                <button onClick={() => addItem(i)}>Adicionar</button>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2>Cotação</h2>
          <label>Fidelidade (meses)</label>
          <input type="number" value={months} onChange={(e) => setMonths(e.target.value)} />
          <label>Horas analista/mês</label>
          <input type="number" value={hours} onChange={(e) => setHours(e.target.value)} />
          <label>Fator câmbio</label>
          <input type="number" value={fx} onChange={(e) => setFx(e.target.value)} />

          <h3>Itens</h3>
          {cart.map((c) => (
            <div key={c.sku} className="item">
              <span>{c.sku}</span>
              <input type="number" value={c.quantity} onChange={(e) => setCart((prev) => prev.map((x) => x.sku === c.sku ? { ...x, quantity: e.target.value } : x))} />
            </div>
          ))}
          <button onClick={calculate}>Calcular</button>

          {result && (
            <div className="result">
              <div>Mensalidade: <b>R$ {result.monthly_price}</b></div>
              <div>Total Contrato: <b>R$ {result.contract_total}</b></div>
              <div>Quote ID (IXC): <b>{result.quote_id}</b></div>
            </div>
          )}
        </div>
      </section>

      {role === "admin" && (
        <section className="grid">
          <div className="card">
            <h2>Admin Configurações</h2>
            <button onClick={loadSettings}>Carregar parâmetros</button>
            {settings && (
              <>
                <label>Imposto (%)</label>
                <input type="number" value={settings.tax_percent} onChange={(e) => setSettings({ ...settings, tax_percent: Number(e.target.value) })} />
                <label>Markup (%)</label>
                <input type="number" value={settings.markup_percent} onChange={(e) => setSettings({ ...settings, markup_percent: Number(e.target.value) })} />
                <label>Custo hora (R$)</label>
                <input type="number" value={settings.hour_cost} onChange={(e) => setSettings({ ...settings, hour_cost: Number(e.target.value) })} />
                <button onClick={saveSettings}>Salvar</button>
              </>
            )}
          </div>
          <div className="card">
            <h2>Admin Importação Price List</h2>
            <input type="file" accept=".xlsx" onChange={importPriceList} />
            <p>Formato esperado: colunas `part`, `desc`, `price` e opcional `type`.</p>
          </div>
        </section>
      )}
    </div>
  );
}
