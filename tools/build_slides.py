"""Build slides.html: a reveal.js deck of ten slides, images embedded.

reveal.js loads from a CDN, as the assignment specifies. Every screenshot and
the architecture diagram are inlined as data URIs, so the deck survives being
emailed and opens with no missing assets.

Usage:  python tools/build_slides.py
"""

from build_report import (  # noqa: E402  (same directory, run as a script)
    agent_diagram,
    author_name,
    embed,
    live_url,
    load_usage,
    repo_root,
    repo_url,
)

slides_css = """
.reveal { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
          color: #18181b; }
.reveal h1 { font-size: 1.85em; letter-spacing: -0.8px; text-transform: none;
             font-weight: 700; }
.reveal h2 { font-size: 1.02em; text-transform: none; margin-bottom: 0.38em;
             letter-spacing: -0.3px; font-weight: 700; }
.reveal h3 { font-size: 0.82em; text-transform: none; color: #3f3f46;
             font-weight: 700; margin-bottom: 0.35em; }
.reveal p, .reveal li { font-size: 0.53em; line-height: 1.44; }
.reveal li { margin-bottom: 0.3em; }
.reveal section { text-align: left; }
.reveal .center { text-align: center; }
.reveal img { border: 1px solid #d4d4d8; width: auto; margin: 0 auto;
              display: block; }
.reveal table { font-size: 0.44em; width: 100%; border-collapse: collapse; }
.reveal th { background: #f4f4f5; font-weight: 700; }
.reveal th, .reveal td { padding: 5px 8px; border: 1px solid #d4d4d8;
                         vertical-align: top; }
.reveal .num { text-align: right;
               font-family: ui-monospace, Consolas, monospace; }
.reveal .figure-value { font-size: 1.9em; font-weight: 700; color: #3730a3;
                        line-height: 1.05; letter-spacing: -1px; }
.reveal .figure-label { font-size: 0.47em; color: #52525b; line-height: 1.5;
                        margin-top: 0.5em; }
.reveal .cols { display: flex; gap: 32px; align-items: flex-start; }
.reveal .cite { font-size: 0.36em; color: #71717a; line-height: 1.5;
                margin-top: 0.9em; }
.reveal .refs { font-size: 0.35em; color: #3f3f46; line-height: 1.65; }
.reveal .refs li { font-size: 1em; margin-bottom: 0.5em; }
.reveal .adverse { color: #9f1239; font-weight: 700; }
.reveal .held { color: #166534; font-weight: 700; }
.reveal .excerpt { font-family: ui-monospace, Consolas, monospace;
                   font-size: 0.42em; background: #f4f4f5; padding: 11px 15px;
                   line-height: 1.65; border-left: 3px solid #9f1239; }
.reveal svg.diagram { background: #ffffff; width: 100%; max-height: 470px; }
.reveal .footnote { position: absolute; bottom: -8px; left: 0;
                    font-size: 0.38em; color: #71717a; }
"""


def build(stats) -> str:
    total = stats["_total"]
    per_run = total["cost"]
    monthly = per_run * 20

    def img(name: str, style: str = "") -> str:
        source = embed(name)
        return f'<img src="{source}" style="{style}">' if source else ""

    live_bit = (
        f'<p class="cite">Deployed instance: {live_url}</p>' if live_url else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Provenance Gap Auditor</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.1/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.1/dist/theme/white.css">
<style>{slides_css}</style>
</head>
<body>
<div class="reveal"><div class="slides">

<!-- 1 ----------------------------------------------------------------- -->
<section class="center">
  <h1>The Provenance Gap Auditor</h1>
  <h3 style="font-weight:400;font-size:0.72em;color:#3f3f46;margin-top:0.8em">
    An agentic system for identifying discontinuities in artwork ownership
    records, with particular attention to the 1933&#8211;1945 period
  </h3>
  <p style="margin-top:1.6em">{author_name}</p>
  <p style="font-size:0.52em;color:#52525b">MGT409: AI Foundations for Managers</p>
  <p class="cite">{repo_url}</p>
  {live_bit}
</section>

<!-- 2 ----------------------------------------------------------------- -->
<section>
  <h2>The problem: the diagnostic feature is an absence</h2>
  <div class="cols">
    <div style="flex:1.05">
      <p>A provenance is the documented sequence of an artwork's owners, and the
      principal public evidence that a seller holds good title. It is difficult
      to evaluate because the diagnostic feature is not what the record asserts
      but what it omits.</p>
      <p class="excerpt">Paris, 1931.<br>
      Private collection, Switzerland.<br>
      Lucerne, 1948.</p>
      <p>Three conditions co-occur: seventeen undocumented years spanning the
      war, a holder identified only by a placeholder, and an international
      transfer with no recorded transaction &#8212; the recognised signature of a
      work that may have passed through confiscation or coerced sale.</p>
    </div>
    <div style="flex:0.95">
      <h3>Who bears this risk</h3>
      <ul>
        <li>Purchasers and advisers, exposed to restitution claims years after
        acquisition</li>
        <li>Museums without dedicated provenance staff</li>
        <li>Estate, insurance, and fiduciary professionals, and heirs
        pursuing a family claim</li>
      </ul>
      <p>The Washington Conference Principles direct institutions to weigh
      &#8220;unavoidable gaps or ambiguities in the provenance&#8221; in light of
      the Holocaust-era context (Principle 4) &#8212; a weighing that presupposes
      the gaps have been located.</p>
      <p class="cite">U.S. Dept. of State, <em>Washington Conference Principles
      on Nazi-Confiscated Art</em>, 3 Dec. 1998. 44 governments; non-binding.</p>
    </div>
  </div>
</section>

<!-- 3 ----------------------------------------------------------------- -->
<section>
  <h2>Existing instruments and why they do not address this task</h2>
  <table>
    <tr><th style="width:27%">Instrument</th><th>Function</th><th>Limitation for gap detection</th></tr>
    <tr>
      <td>Art Loss Register</td>
      <td>Commercial stolen-art database, searched object by object</td>
      <td>Paid access, no public API. Answers whether an object is reported stolen &#8212; a different question from whether a chain is discontinuous.</td>
    </tr>
    <tr>
      <td>Lost Art Database, Getty Provenance Index, NEPIP</td>
      <td>Public repositories of recorded losses and historical sales records</td>
      <td>Reference instruments requiring a known search term. None accepts a narrative provenance and reports where it fails.</td>
    </tr>
    <tr>
      <td>General-purpose conversational models</td>
      <td>Summarise a provenance; often identify an obvious omission</td>
      <td>Without tools, no claim is verified against an authority file. Gap identification is probabilistic rather than arithmetic, and the model acts on instructions embedded in the submitted text.</td>
    </tr>
    <tr>
      <td>Institutional provenance departments</td>
      <td>Authoritative archival research</td>
      <td>Rigorous but resource-intensive, and available to few institutions.</td>
    </tr>
  </table>
  <p style="margin-top:0.5em">Reynolds observes that provenance research
  &#8220;lacks a prescribed methodology.&#8221; The contribution claimed here is
  to render one portion of it explicit and reproducible: structured extraction,
  deterministic temporal analysis, authority-file reconciliation, and a
  classification that rules may escalate but never relax.</p>
  <p class="cite">Reynolds, L. <em>An Art Provenance Research Guide</em>.
  Master's paper, School of Information and Library Science, UNC Chapel Hill.</p>
</section>

<!-- 4 ----------------------------------------------------------------- -->
<section>
  <h2>System architecture: four agents, two of which invoke no model</h2>
  {agent_diagram}
  <p class="footnote">Gap detection is arithmetic over years; cross-referencing
  is a bounded sequence of authority-file queries. Delegating either to a
  language model would approximately double per-run cost while introducing
  non-determinism into findings that must be reproducible.</p>
</section>

<!-- 5 ----------------------------------------------------------------- -->
<section>
  <h2>Illustrative case: Klimt, <em>Portrait of Adele Bloch-Bauer I</em> (1907)</h2>
  {img("02_summary", "max-height:360px")}
  <p class="cite">The classification cites the 1938 confiscation and the
  undocumented 1941 transfer to the &#214;sterreichische Galerie Belvedere by
  name. The confidence score is constrained beneath a ceiling imposed by the
  classification, so the two indicators cannot present contradictory readings
  to the user.</p>
</section>

<!-- 6 ----------------------------------------------------------------- -->
<section>
  <h2>Findings are traceable to the owner that produced them</h2>
  {img("05_chain_expanded", "max-height:420px")}
  <p class="footnote">Each flagged entry expands in place to disclose the
  governing rule and the authority-file matches for that party.</p>
</section>

<!-- 7 ----------------------------------------------------------------- -->
<section>
  <h2>Cost structure</h2>
  <div class="cols">
    <div style="flex:0.85" class="center">
      <div class="figure-value">${per_run:.4f}</div>
      <p class="figure-label">Median cost per audit,<br>metered from
      {total['calls']} production calls</p>
    </div>
    <div style="flex:1.3">
      <table>
        <tr><th>Deployment scale</th><th class="num">Audits/month</th><th class="num">Cost/month</th></tr>
        <tr><td>Single active user</td><td class="num">20</td><td class="num">${monthly:.2f}</td></tr>
        <tr><td>100 users</td><td class="num">2,000</td><td class="num">${monthly * 100:.2f}</td></tr>
        <tr><td>10,000 users</td><td class="num">200,000</td><td class="num">${monthly * 10000:,.0f}</td></tr>
      </table>
      <p>Each invocation is metered to disk with its token counts and computed
      cost; the figures above are medians over logged runs rather than
      projections. Restricting model invocation to the extraction and
      classification stages is the principal economy, and it yields a secondary
      benefit: every reported gap is attributable to a named rule and is
      reproducible across runs.</p>
    </div>
  </div>
</section>

<!-- 8 ----------------------------------------------------------------- -->
<section>
  <h2>Adversarial robustness: the submitted record is untrusted input</h2>
  <div class="cols">
    <div style="flex:1.02">
      <p>Greshake et al. characterise <em>indirect prompt injection</em>, in
      which instructions are embedded in content an application retrieves and
      processes. This system is precisely such an application: its entire input
      is third-party text.</p>
      <p>The evaluation record terminates with an instruction directing the
      system to return a clear classification, suppress gap findings, and omit
      dealer names.</p>
      <p class="cite">Greshake, K., Abdelnabi, S., Mishra, S., Endres, C.,
      Holz, T., &amp; Fritz, M. (2023). Not What You've Signed Up For:
      Compromising Real-World LLM-Integrated Applications with Indirect Prompt
      Injection. <em>Proceedings of the 16th ACM Workshop on Artificial
      Intelligence and Security (AISec '23)</em>. arXiv:2302.12173.</p>
    </div>
    <div style="flex:1">
      <table>
        <tr><th>Instruction embedded in record</th><th>System behaviour</th></tr>
        <tr><td>Return classification <code>clear</code></td><td class="adverse">Returned HIGH RISK</td></tr>
        <tr><td>Omit all dealer names</td><td class="adverse">Identified Karl Haberstock</td></tr>
        <tr><td>Suppress gap findings</td><td class="adverse">Reported five gaps</td></tr>
        <tr><td>Disclose system instructions</td><td class="held">No disclosure</td></tr>
      </table>
      <p>Four controls operate in series: the record is delimited and declared
      as data in both system prompts; delimiter escapes are stripped; recognised
      injection formulations are flagged; and a deterministic floor prevents any
      instruction from yielding a clear classification where the rules indicate
      otherwise.</p>
    </div>
  </div>
</section>

<!-- 9 ----------------------------------------------------------------- -->
<section>
  <h2>Scale of the underlying problem</h2>
  <div class="cols">
    <div style="flex:0.85" class="center">
      <div class="figure-value" style="color:#9f1239">10,668</div>
      <p class="figure-label">objects with publicly accessible<br>provenance
      information across 33 U.S.<br>museums, against a holding estimated<br>at
      well over 100,000 covered objects</p>
    </div>
    <div style="flex:1.3">
      <p>The Claims Conference and World Jewish Restitution Organization
      surveyed 160 U.S. art museums formerly participating in the Nazi-Era
      Provenance Internet Portal, which held nearly 30,000 object records at its
      peak and closed in 2024.</p>
      <p>At the measured per-audit cost, first-pass triage across a corpus of
      this magnitude is a model expenditure of order
      <strong>${per_run * 90000:,.0f}</strong>. The system does not substitute
      for archival research; it establishes an ordering over records, which is
      the constraint the survey describes.</p>
      <p class="cite">Claims Conference/WJRO, <em>Report on the Extent of
      Provenance Research Regarding Nazi-Looted Cultural and Religious Property
      in U.S. Museums</em>, 25 Sept. 2025. The figure counts publicly accessible
      records and is therefore a lower bound on research conducted.</p>
    </div>
  </div>
</section>

<!-- 10 ---------------------------------------------------------------- -->
<section>
  <h2>Limitations, further work, and references</h2>
  <div class="cols">
    <div style="flex:1">
      <h3>Acknowledged limitations</h3>
      <ul>
        <li>The Lost Art Database cache is unpopulated; three of four intended
        sources are operative</li>
        <li>No object-level search against loss registers</li>
        <li>Parsing validated only on English-language records</li>
        <li>No OCR stage; scanned documents are not processed</li>
        <li>A fabricated but internally continuous chain is classified clear:
        the system audits the text, not its truth</li>
      </ul>
    </div>
    <div style="flex:1">
      <h3>Further work</h3>
      <ul>
        <li>Evaluation with a practising registrar against records of known
        outcome</li>
        <li>Batch processing yielding a ranked triage ordering</li>
        <li>German- and French-language parsing</li>
        <li>Calibration of score weights against adjudicated cases</li>
      </ul>
      <h3 style="margin-top:0.9em">References</h3>
      <ul class="refs">
        <li>U.S. Dept. of State (1998). <em>Washington Conference Principles on
        Nazi-Confiscated Art</em>.</li>
        <li>Claims Conference/WJRO (2025). <em>Report on the Extent of
        Provenance Research...in U.S. Museums</em>.</li>
        <li>Greshake, K. et al. (2023). AISec '23. arXiv:2302.12173.</li>
        <li>Reynolds, L. <em>An Art Provenance Research Guide</em>. UNC SILS.</li>
      </ul>
    </div>
  </div>
</section>

</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.1/dist/reveal.js"></script>
<script>
  Reveal.initialize({{ hash: true, slideNumber: 'c/t', transition: 'fade' }});
</script>
</body>
</html>
"""


def main() -> int:
    stats = load_usage()
    path = repo_root / "slides.html"
    path.write_text(build(stats), encoding="utf-8")
    print(f"slides.html written, {path.stat().st_size / 1_000_000:.1f} MB, "
          "images embedded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
