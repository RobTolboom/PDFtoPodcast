<rules owner="Rob Tolboom" project="repo-root" version="2025-10-13">
  <meta_rules>
    <rule_1>Vraag altijd y/n-bevestiging vóór het uitvoeren van bestands-, git-, build- of CI-acties.</rule_1>
    <rule_2>Gebruiker heeft finale autoriteit; wijzig geen plan zonder expliciet akkoord.</rule_2>
    <rule_3>Rapporteer eerst een kort uitvoeringsplan met de exacte commando’s; wacht op akkoord.</rule_3>
    <rule_4>Volg repository policies en @CONTRIBUTING.md; herinterpreteer of wijzig deze regels niet.</rule_4>
    <rule_5>Toon aan het begin van ELKE respons exact de sectietitels en alle toepasselijke regels hieronder, woordelijk en in deze volgorde.</rule_5>
  </meta_rules>

  <workflows>
    <start_van_dag>
      <step_1>git pull origin main</step_1>
      <step_2>Als dependencies gewijzigd zijn: make install-dev</step_2>
    </start_van_dag>

    <na_code_wijziging>
      <step_1>make format   <!-- code formatter --></step_1>
      <step_2>make lint     <!-- statische checks --></step_2>
      <step_3>make test-fast<!-- snelle feedback --></step_3>
    </na_code_wijziging>

    <voor_commit>
      <step_1>make commit   <!-- pre-commit voorbereiding --></step_1>
      <step_2>git commit -m "type: beschrijving"</step_2>
    </voor_commit>

    <voor_push>
      <step_1>make ci       <!-- simuleer CI lokaal --></step_1>
      <step_2>git push</step_2>
    </voor_push>
  </workflows>

  <feature_planning>
    <planfase>
      <rule>Maak een feature-markdown in de map "features" met doel, scope, takenlijst, risico’s, en acceptatiecriteria.</rule>
    </planfase>
    <ontwikkeling>
      <rule>Werk in de juiste branch; maak er één indien nodig en noteer de branchnaam in het feature-document.</rule>
      <rule>Commit regelmatig met duidelijke beschrijvingen; voer format/lint/tests vóór elke commit uit.</rule>
      <rule>Push en PR uitsluitend na expliciete goedkeuring van de gebruiker.</rule>
    </ontwikkeling>
  </feature_planning>

  <change_management>
    <bij_elke_wijziging>
      <rule>Update CHANGELOG.md onder “Unreleased”.</rule>
      <rule>Update relevante documentatie (README.md, ARCHITECTURE.md, enz.).</rule>
      <rule>Voeg passende tests toe of werk bestaande tests bij.</rule>
      <rule>Update API.md indien van toepassing.</rule>
    </bij_elke_wijziging>
  </change_management>

  <display_policy>
    <condities>
      <rule>Als de taak bestands-/git-/build-/CI-acties of branch/PR omvat: toon alle regels in &lt;meta_rules&gt;, de relevante &lt;workflows&gt;-stappen en &lt;change_management&gt;.</rule>
      <rule>In andere gevallen: toon alleen &lt;meta_rules&gt; en de sectiekoppen van dit document.</rule>
    </condities>
    <verbatim>Weergave moet woordelijk zijn; geen parafrasering of samenvatting buiten de condities hierboven.</verbatim>
    <self_reference>Deze &lt;display_policy&gt; valt zelf onder de weergave-eis.</self_reference>
  </display_policy>
</rules>
