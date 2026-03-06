"""Lattes XML extractor.

Accepts:
  - .xml file (Lattes XML export)
  - .zip file containing a single .xml (as exported from lattes.cnpq.br)

Extracts relevant sections and formats them as plain text for the pipeline.
"""
import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_lattes_xml(content: bytes, filename: str) -> str:
    """Parse Lattes XML (or ZIP containing XML) and return structured text."""
    xml_bytes = _load_xml_bytes(content, filename)
    root = ET.fromstring(xml_bytes)

    if root.tag != "CURRICULO-VITAE":
        raise ValueError(f"XML não reconhecido como Lattes: root tag = {root.tag}")

    parts = [
        f"SOURCE: lattes_xml",
        f"TYPE: lattes_xml",
        f"LATTES_ID: {root.attrib.get('NUMERO-IDENTIFICADOR', '')}",
        f"UPDATED: {root.attrib.get('DATA-ATUALIZACAO', '')}",
        "",
    ]

    dg = root.find("DADOS-GERAIS")
    if dg is not None:
        parts += _dados_gerais(dg)

    pb = root.find("PRODUCAO-BIBLIOGRAFICA")
    if pb is not None:
        parts += _producao_bibliografica(pb)

    pt = root.find("PRODUCAO-TECNICA")
    if pt is not None:
        parts += _producao_tecnica(pt)

    dc = root.find("DADOS-COMPLEMENTARES")
    if dc is not None:
        parts += _dados_complementares(dc)

    return "\n".join(parts)


# ── Internal parsers ───────────────────────────────────────────────────────────

def _load_xml_bytes(content: bytes, filename: str) -> bytes:
    ext = Path(filename).suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                raise ValueError("ZIP não contém nenhum arquivo .xml")
            return zf.read(xml_names[0])
    return content


def _dados_gerais(dg: ET.Element) -> list[str]:
    parts = ["=== DADOS GERAIS ==="]
    parts.append(f"Nome: {dg.attrib.get('NOME-COMPLETO', '')}")
    parts.append(f"Citação: {dg.attrib.get('NOME-EM-CITACOES-BIBLIOGRAFICAS', '')}")
    orcid = dg.attrib.get("ORCID-ID", "")
    if orcid:
        parts.append(f"ORCID: {orcid}")

    resumo = dg.find("RESUMO-CV")
    if resumo is not None:
        text = resumo.attrib.get("TEXTO-RESUMO-CV-RH", "")
        if text.strip():
            parts.append(f"\nResumo:\n{text}")

    parts += _formacao(dg.find("FORMACAO-ACADEMICA-TITULACAO"))
    parts += _atuacoes(dg.find("ATUACOES-PROFISSIONAIS"))
    parts += _areas_atuacao(dg.find("AREAS-DE-ATUACAO"))
    parts += _premios(dg.find("PREMIOS-TITULOS"))
    parts.append("")
    return parts


def _formacao(node: ET.Element | None) -> list[str]:
    if node is None:
        return []
    parts = ["\n--- Formação Acadêmica ---"]
    level_map = {
        "GRADUACAO": "Graduação",
        "ESPECIALIZACAO": "Especialização",
        "MESTRADO": "Mestrado",
        "DOUTORADO": "Doutorado",
        "POS-DOUTORADO": "Pós-Doutorado",
        "LIVRE-DOCENCIA": "Livre-Docência",
    }
    for child in node:
        label = level_map.get(child.tag, child.tag)
        curso = child.attrib.get("NOME-CURSO", "")
        inst = child.attrib.get("NOME-INSTITUICAO", "")
        inicio = child.attrib.get("ANO-DE-INICIO", "")
        fim = child.attrib.get("ANO-DE-CONCLUSAO", "") or child.attrib.get("ANO-DE-OBTENCAO-DO-TITULO", "")
        titulo = (
            child.attrib.get("TITULO-DA-DISSERTACAO-TESE", "")
            or child.attrib.get("TITULO-DO-TRABALHO-DE-CONCLUSAO-DE-CURSO", "")
            or child.attrib.get("TITULO-DO-TRABALHO", "")
        )
        orientador = (
            child.attrib.get("NOME-COMPLETO-DO-ORIENTADOR", "")
            or child.attrib.get("NOME-DO-ORIENTADOR", "")
        )
        period = f"{inicio}–{fim}" if inicio else fim
        line = f"  {label}: {curso} — {inst} ({period})"
        if titulo:
            line += f"\n    Título: {titulo}"
        if orientador:
            line += f"\n    Orientador: {orientador}"
        parts.append(line)
    return parts


def _atuacoes(node: ET.Element | None) -> list[str]:
    if node is None:
        return []
    parts = ["\n--- Atuações Profissionais ---"]
    for ap in node.findall("ATUACAO-PROFISSIONAL"):
        inst = ap.attrib.get("NOME-INSTITUICAO", "")
        vinculos = ap.findall(".//VINCULOS")
        for v in vinculos:
            cargo = v.attrib.get("OUTRO-ENQUADRAMENTO-FUNCIONAL-INFORMADO", "") or v.attrib.get("ENQUADRAMENTO-FUNCIONAL", "")
            inicio = v.attrib.get("ANO-INICIO", "")
            fim = v.attrib.get("ANO-FIM", "") or "atual"
            period = f"{inicio}–{fim}" if inicio else ""
            if cargo:
                parts.append(f"  {inst}: {cargo} ({period})")
                break
        else:
            if inst:
                parts.append(f"  {inst}")
    return parts


def _areas_atuacao(node: ET.Element | None) -> list[str]:
    if node is None:
        return []
    areas = []
    for a in node.findall("AREA-DE-ATUACAO"):
        grande = a.attrib.get("NOME-GRANDE-AREA-DO-CONHECIMENTO", "")
        area = a.attrib.get("NOME-DA-AREA-DO-CONHECIMENTO", "")
        sub = a.attrib.get("NOME-DA-SUB-AREA-DO-CONHECIMENTO", "")
        label = " > ".join(filter(None, [grande, area, sub]))
        if label:
            areas.append(label)
    if not areas:
        return []
    return ["\n--- Áreas de Atuação ---"] + [f"  {a}" for a in areas]


def _premios(node: ET.Element | None) -> list[str]:
    if node is None:
        return []
    parts = []
    for p in node.findall("PREMIO-TITULO"):
        nome = p.attrib.get("NOME-DO-PREMIO-OU-TITULO", "")
        ano = p.attrib.get("ANO-DA-PREMIACAO", "")
        entidade = p.attrib.get("NOME-DA-ENTIDADE-PROMOTORA", "")
        if nome:
            parts.append(f"  {ano} — {nome} ({entidade})")
    if parts:
        return ["\n--- Prêmios e Títulos ---"] + parts
    return []


def _producao_bibliografica(pb: ET.Element) -> list[str]:
    parts = ["=== PRODUÇÃO BIBLIOGRÁFICA ==="]

    artigos = pb.find("ARTIGOS-PUBLICADOS")
    if artigos is not None:
        items = list(artigos)
        parts.append(f"\n--- Artigos Publicados ({len(items)}) ---")
        for art in items:
            db = art.find("DADOS-BASICOS-DO-ARTIGO")
            det = art.find("DETALHAMENTO-DO-ARTIGO")
            if db is None:
                continue
            titulo = db.attrib.get("TITULO-DO-ARTIGO", "")
            ano = db.attrib.get("ANO-DO-ARTIGO", "")
            doi = db.attrib.get("DOI", "")
            periodico = det.attrib.get("TITULO-DO-PERIODICO-OU-REVISTA", "") if det is not None else ""
            autores = ", ".join(
                a.attrib.get("NOME-PARA-CITACAO", "") for a in art.findall("AUTORES")
            )
            line = f"  [{ano}] {titulo}"
            if periodico:
                line += f" — {periodico}"
            if autores:
                line += f"\n    Autores: {autores}"
            if doi:
                line += f"\n    DOI: {doi}"
            parts.append(line)

    eventos = pb.find("TRABALHOS-EM-EVENTOS")
    if eventos is not None:
        items = list(eventos)
        parts.append(f"\n--- Trabalhos em Eventos ({len(items)}) ---")
        for ev in items:
            db = ev.find("DADOS-BASICOS-DO-TRABALHO")
            det = ev.find("DETALHAMENTO-DO-TRABALHO")
            if db is None:
                continue
            titulo = db.attrib.get("TITULO-DO-TRABALHO", "")
            ano = db.attrib.get("ANO-DO-TRABALHO", "")
            evento = det.attrib.get("NOME-DO-EVENTO", "") if det is not None else ""
            autores = ", ".join(
                a.attrib.get("NOME-PARA-CITACAO", "") for a in ev.findall("AUTORES")
            )
            line = f"  [{ano}] {titulo}"
            if evento:
                line += f" — {evento}"
            if autores:
                line += f"\n    Autores: {autores}"
            parts.append(line)

    livros = pb.find("LIVROS-E-CAPITULOS")
    if livros is not None:
        livros_pub = livros.findall("LIVROS-PUBLICADOS-OU-ORGANIZADOS")
        capitulos = livros.findall("CAPITULOS-DE-LIVROS-PUBLICADOS")
        total = len(livros_pub) + len(capitulos)
        if total:
            parts.append(f"\n--- Livros e Capítulos ({total}) ---")
            for lv in livros_pub:
                db = lv.find("DADOS-BASICOS-DO-LIVRO")
                det = lv.find("DETALHAMENTO-DO-LIVRO")
                if db is None:
                    continue
                titulo = db.attrib.get("TITULO-DO-LIVRO", "")
                ano = db.attrib.get("ANO", "")
                editora = det.attrib.get("NOME-DA-EDITORA", "") if det is not None else ""
                parts.append(f"  [{ano}] {titulo} — {editora}")
            for cap in capitulos:
                db = cap.find("DADOS-BASICOS-DO-CAPITULO")
                det = cap.find("DETALHAMENTO-DO-CAPITULO")
                if db is None:
                    continue
                titulo = db.attrib.get("TITULO-DO-CAPITULO-DO-LIVRO", "")
                ano = db.attrib.get("ANO", "")
                livro_nome = det.attrib.get("TITULO-DO-LIVRO", "") if det is not None else ""
                parts.append(f"  [{ano}] (Capítulo) {titulo} in {livro_nome}")

    parts.append("")
    return parts


def _producao_tecnica(pt: ET.Element) -> list[str]:
    parts = []
    software = list(pt.findall("SOFTWARE"))
    if software:
        parts.append(f"\n--- Software ({len(software)}) ---")
        for sw in software:
            db = sw.find("DADOS-BASICOS-DO-SOFTWARE")
            if db is None:
                continue
            titulo = db.attrib.get("TITULO-DO-SOFTWARE", "")
            ano = db.attrib.get("ANO", "")
            parts.append(f"  [{ano}] {titulo}")
    if parts:
        return ["=== PRODUÇÃO TÉCNICA ==="] + parts + [""]
    return []


def _dados_complementares(dc: ET.Element) -> list[str]:
    parts = []

    orientacoes = dc.find("ORIENTACOES-CONCLUIDAS")
    if orientacoes is not None:
        mestrados = orientacoes.findall("ORIENTACOES-CONCLUIDAS-PARA-MESTRADO")
        doutorados = orientacoes.findall("ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO")
        ic = orientacoes.findall("OUTRAS-ORIENTACOES-CONCLUIDAS")
        total = len(mestrados) + len(doutorados)
        if total:
            parts.append(f"--- Orientações Concluídas ---")
            if mestrados:
                parts.append(f"  Mestrado: {len(mestrados)}")
            if doutorados:
                parts.append(f"  Doutorado: {len(doutorados)}")

    bancas = dc.find("PARTICIPACAO-EM-BANCA-TRABALHOS-CONCLUSAO")
    if bancas is not None:
        total = len(list(bancas))
        if total:
            parts.append(f"--- Bancas de Trabalhos de Conclusão: {total} ---")

    eventos_org = dc.find("EVENTOS-ARTIGOS")
    if eventos_org is not None:
        total = len(list(eventos_org))
        if total:
            parts.append(f"--- Participação em Eventos/Artigos: {total} ---")

    if parts:
        return ["=== DADOS COMPLEMENTARES ==="] + parts + [""]
    return []
