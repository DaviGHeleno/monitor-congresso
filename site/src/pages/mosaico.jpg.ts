// Copia a grade de fotos gerada pelo coletor para o site publicado (/mosaico.jpg).
import fs from "node:fs";
import { caminhoMosaico } from "../lib/dados";

export function GET() {
  const arquivo = caminhoMosaico();
  const corpo = fs.existsSync(arquivo) ? fs.readFileSync(arquivo) : new Uint8Array();
  return new Response(corpo, { headers: { "Content-Type": "image/jpeg" } });
}
