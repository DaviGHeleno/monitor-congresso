// Versão alta do mosaico, para celular (/mosaico-celular.jpg).
import fs from "node:fs";
import { caminhoMosaico } from "../lib/dados";

export function GET() {
  const arquivo = caminhoMosaico(true);
  const corpo = fs.existsSync(arquivo) ? fs.readFileSync(arquivo) : new Uint8Array();
  return new Response(corpo, { headers: { "Content-Type": "image/jpeg" } });
}
