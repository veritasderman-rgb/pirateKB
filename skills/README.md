# Skills pro Claude: Pirátská znalostní báze

Balíček [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
pro Clauda. Skill je složka se souborem `SKILL.md`, který Claude načte, když se úkol hodí
k jeho popisu (`description` ve frontmatter). Skills popisují *postup* (které tooly
znalostní báze volat, jak citovat, co kontrolovat). Data dodává MCP server `piratekb`.

| Skill | K čemu |
|---|---|
| [`piratekb-tiskova-zprava`](piratekb-tiskova-zprava/SKILL.md) | návrh tiskové zprávy podle struktury TZ na pirati.cz, s ověřeným postojem, citacemi a kontrolou proti programu; výstup ke schválení mediálním odborem |
| [`piratekb-brief`](piratekb-brief/SKILL.md) | interní brief k tématu: postoj a autorita, fakta, co jsme udělali, argumenty, kdo mluví (`find_expert`), co chybí |
| [`piratekb-socialni-site`](piratekb-socialni-site/SKILL.md) | posty (FB, IG, X) a scénáře Reels podle brand pravidel Pirátů |

Všechny skills obsahují sekci **„Kdy použít Hlídač státu“** (smlouvy, zakázky, dotace,
sponzoři stran z MCP serveru hlidacstatu.cz, pokud ho máte připojený) a **„Když KB
odpověď nemá“** (`find_expert`, `report_gap`).

## Předpoklady

1. **Připojená znalostní báze** jako MCP konektor (claude.ai / Claude Desktop:
   Settings → Connectors → Add custom connector s adresou serveru `…/mcp`; Claude Code:
   `claude mcp add --transport http piratekb https://<server>/mcp`). Návod je
   v [docs/pripojeni/README.md](../docs/pripojeni/README.md). Bez konektoru skill
   jen upozorní, že data nemá.
2. Volitelně **MCP Hlídače státu** pro fakta o veřejných penězích.
3. V Claude zapnuté **Skills** (Settings → Capabilities → Code execution and file
   creation / Skills; dostupnost podle tarifu). (ověřit: přesné umístění přepínače se mění.)

## Instalace

### Claude Desktop a claude.ai

Každý skill se nahrává jako ZIP se složkou skillu:

```sh
cd skills
for s in piratekb-tiskova-zprava piratekb-brief piratekb-socialni-site; do
  zip -r "$s.zip" "$s"
done
```

Pak v Claude: **Settings → Capabilities → Skills → Upload skill** (případně Settings →
Skills) a nahrajte jednotlivé ZIPy. Skill se po nahrání zapne přepínačem. Na tarifech
Team/Enterprise může skills nahrát správce pro celou organizaci. (ověřit: názvy položek
menu podle aktuální verze aplikace.)

### Claude Code

Zkopírujte složky do osobních skills (platí pro všechny projekty):

```sh
mkdir -p ~/.claude/skills
cp -r skills/piratekb-* ~/.claude/skills/
```

nebo jen pro jeden projekt do `.claude/skills/` v kořeni projektu. Claude Code je načte
při dalším spuštění. Ověříte to dotazem „jaké máš skills?“ nebo v nabídce `/`.

### Agent SDK / API

Složky lze použít i jako skills v Claude Agent SDK (adresář `.claude/skills/`) nebo
nahrát přes Skills API. Viz [dokumentace Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview).

## Použití

Stačí psát přirozeně, Claude skill vybere podle popisu:

- „Napiš tiskovou zprávu k tomu, že vláda škrtla 14 miliard na dostupné bydlení, mluvčí Vendula Svobodová.“
- „Připrav mi brief k Chat Control, zítra o tom mluvím v rádiu.“
- „Udělej instagramový karusel a scénář reelsu o transparentnosti veřejných zakázek.“

Stejné postupy jsou na serveru i jako MCP prompty (`tiskova_zprava`, `brief_k_tematu`,
`social_post`, `reels_scenar`). Skills navíc fungují bez ručního výběru promptu a obsahují
pravidla pro Hlídač státu.

## Údržba

Zdrojem textů jsou šablony `server/prompts/*.md` a prompty v `server/mcp_server.py`.
Při změně šablony nebo názvů toolů upravte i skills. Frontmatter musí mít `name` (malá
písmena a pomlčky, shodné s názvem složky) a `description` (co skill dělá a kdy ho
použít, max. 1 024 znaků).
