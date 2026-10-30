Call the web theme setting what it is: the home page style

**What a user sees today**

The Settings page offers "Web Interface Theme", with the choices "Default Web Theme" and "Modern Theme". But the choice only changes the home page. The Modern theme supplies its own home page (`themes/Modern/main.html.j2` and its scripts), and every other page (Settings, Schedule, Policy, Vehicles, Graphs, Debug) comes from `themes/Default/` under either choice. So "theme" promises more than it delivers. Someone picking Modern for its look finds that the rest of the interface hasn't changed.

The two places that pick a theme when none has been saved also disagree:
- Since 4ba5c7c9 (August 2026), the server falls back to Default when `webControlTheme` has never been saved. The commit says: "Modern only defines a handful of templates and falls through to Default for everything else."
- The Settings page still preselects Modern in that case (`settings.html.j2`, `master.settings.get("webControlTheme", "Modern")`). A fresh install shows the Default home page, but its Settings page says Modern is selected, and the first time anyone saves settings, the home page silently switches to Modern.

**Proposal**

1. **Fix the mismatch toward Modern,** the intended default since v1.2.3 (93c49642): have the server also fall back to Modern when nothing has been saved, so a fresh install shows the home page its Settings page displays, and saving settings doesn't change it. 4ba5c7c9's point, that Modern defines only a handful of templates, is met by #2: the setting only ever chooses the home page, and every other page comes from the shared base either way.
2. **Narrow the setting to what it does.** Label it "Home page style", with choices such as "Classic" and "Modern", and say on the page that it changes the home page only. The setting key (`webControlTheme`) and the theme folders can stay as they are, so existing settings keep working.
3. **Optionally,** rename `themes/Default/` to reflect its real role as the base every page comes from, keeping a fallback for the old name. This is internal only; it matters only if more themes are expected.

This issue isn't about retiring either home page. Both stay available, and #330's plan to remove the legacy UI once Modern covers every use case is a separate question.

Context: I'm exploring making the home, Policy and Vehicles pages update live from the same JSON APIs other clients use. That work would give both home pages the same live data, and would list every charging point (Gen3 units and EVSEs controlled through the car, not only Gen2 TWCs). It wouldn't depend on this issue, but exploring it is how the gap became visible.
