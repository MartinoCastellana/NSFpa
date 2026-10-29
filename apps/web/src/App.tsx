import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api, Evidence } from "./lib/api";
import { StatusPill } from "./components/StatusPill";
import "./styles.css";

function Layout({ children }: { children: React.ReactNode }) {
  return <div className="shell"><header><div className="brand"><span className="brand-mark">◈</span><span>Privacy OCR</span></div><nav><Link to="/">Dashboard</Link><Link to="/new">Nuova richiesta</Link></nav><span className="secure">● locale / fail-closed</span></header><main>{children}</main></div>;
}

function Dashboard() {
  const navigate = useNavigate();
  const create = useMutation({ mutationFn: api.createRequest, onSuccess: (item) => navigate(`/requests/${item.id}`) });
  return <section className="hero"><div><p className="eyebrow">WORKSPACE PRIVATO</p><h1>Trasforma documenti sensibili in dati utilizzabili.</h1><p className="lede">OCR, evidenze e pseudonimizzazione avvengono localmente. L’invio esterno resta bloccato finché il testo safe non supera revisione e validazione.</p><button onClick={() => create.mutate()} disabled={create.isPending}>{create.isPending ? "Creo…" : "Crea richiesta"}</button></div><div className="metric-card"><span>Controllo outbound</span><strong>SOLO TESTO</strong><small>PDF, immagini e OCR originale non entrano mai nel payload provider.</small></div></section>;
}

function NewRequest() {
  const navigate = useNavigate();
  const { register, handleSubmit } = useForm<{ policy: string }>({ defaultValues: { policy: "Pseudonimizzazione italiana · approvazione manuale obbligatoria" } });
  const create = useMutation({ mutationFn: api.createRequest, onSuccess: (item) => navigate(`/requests/${item.id}`) });
  return <section className="panel narrow"><p className="eyebrow">NUOVA RICHIESTA</p><h2>Definisci lo scope di lavoro</h2><form onSubmit={handleSubmit(() => create.mutate())}><label>Policy attiva<input {...register("policy")} readOnly /></label><label className="check"><input type="checkbox" checked readOnly /> Richiedi revisione umana prima di qualsiasi invio</label><button type="submit">Continua</button></form></section>;
}

function RequestWorkspace() {
  const { requestId } = useParams<{ requestId: string }>();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const documents = useQuery({ queryKey: ["documents", requestId], queryFn: () => api.documents(requestId!), enabled: !!requestId });
  const evidences = useQuery({ queryKey: ["evidences", requestId], queryFn: () => api.evidences(requestId!), enabled: !!requestId });
  const safeText = useQuery({ queryKey: ["safe", requestId], queryFn: () => api.safeText(requestId!), enabled: !!requestId, retry: false });
  const run = useMutation({ mutationFn: async () => { if (!file) throw new Error("Seleziona un documento"); const doc = await api.upload(requestId!, file); await api.extract(doc.id); await api.detect(requestId!); await api.approve(requestId!); await api.pseudonymize(requestId!); return api.validate(requestId!); }, onSuccess: () => { setMessage("Preflight completato: verifica il testo safe prima dell’invio."); queryClient.invalidateQueries({ queryKey: ["documents", requestId] }); queryClient.invalidateQueries({ queryKey: ["evidences", requestId] }); queryClient.invalidateQueries({ queryKey: ["safe", requestId] }); }, onError: (error) => setMessage(error instanceof Error ? error.message : "Operazione non riuscita") });
  const send = useMutation({ mutationFn: () => api.send(requestId!), onSuccess: () => setMessage("Risposta pseudonimizzata ricevuta."), onError: (error) => setMessage(error instanceof Error ? error.message : "Invio bloccato") });
  return <section><div className="workspace-head"><div><p className="eyebrow">REQUEST SCOPE</p><h2>{requestId}</h2></div><span className="gate">API gate: {safeText.data?.approved ? "READY" : "REVIEW"}</span></div><div className="steps"><span className="active">1 · upload</span><span>2 · evidence</span><span>3 · safe text</span><span>4 · outbound</span></div><div className="grid"><div className="panel"><h3>Documento locale</h3><p className="muted">Il file resta nel volume privato del server.</p><label className="drop"><input type="file" accept="application/pdf,image/png,image/jpeg,text/plain" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />{file ? file.name : "Scegli PDF, immagine o fixture testo"}</label><button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? "Elaboro localmente…" : "Estrai e prepara preflight"}</button>{documents.data?.map((doc) => <div className="file-row" key={doc.id}><span>{doc.original_name}</span><StatusPill status={doc.status} /></div>)}</div><div className="panel"><h3>Evidenze rilevate</h3>{evidences.isLoading ? <p className="muted">In attesa del rilevamento…</p> : evidences.data?.length ? <div className="evidence-list">{evidences.data.map((item: Evidence) => <div className="evidence" key={item.id}><div><strong>{item.entity_type}</strong><span>{item.semantic_role ?? "review"}</span></div><small>{item.detector} · {Math.round(item.score * 100)}% · {item.review_status}</small></div>)}</div> : <p className="muted">Nessuna evidenza ancora disponibile.</p>}</div><div className="panel span-2"><div className="panel-title"><div><h3>Preflight — testo pseudonimizzato</h3><p className="muted">Questa è l’unica superficie documentale autorizzabile verso il provider.</p></div>{safeText.data && <StatusPill status={safeText.data.validation_report.status as string ?? "PENDING"} />}</div><pre className="safe-text">{safeText.data?.text ?? "Completa la pipeline per visualizzare il testo safe."}</pre><div className="actions"><button className="secondary" onClick={() => send.mutate()} disabled={!safeText.data?.approved || send.isPending}>{send.isPending ? "Invio…" : "Approva e invia solo testo"}</button></div></div></div>{message && <div className="notice">{message}</div>}</section>;
}

export default function App() { return <Layout><Routes><Route path="/" element={<Dashboard />} /><Route path="/new" element={<NewRequest />} /><Route path="/requests/:requestId" element={<RequestWorkspace />} /></Routes></Layout>; }
