// Todas as despesas da cota de um parlamentar (formato compacto do coletor), lidas pela página de gastos.
import { gastosDetalheTexto, idsComGastos } from "../../../../lib/dados";

export function getStaticPaths() {
  return (["camara", "senado"] as const).flatMap((casa) => idsComGastos(casa).map((id) => ({ params: { casa, id: String(id) } })));
}

export function GET({ params }: { params: { casa: "camara" | "senado"; id: string } }) {
  return new Response(gastosDetalheTexto(params.casa, Number(params.id)), { headers: { "Content-Type": "application/json; charset=utf-8" } });
}
