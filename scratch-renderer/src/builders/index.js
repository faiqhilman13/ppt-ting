const sectionBreak = require("./sectionBreak");
const executiveSummary = require("./executiveSummary");
const comparison = require("./comparison");
const timeline = require("./timeline");
const kpi = require("./kpi");
const agenda = require("./agenda");
const quote = require("./quote");
const closing = require("./closing");
const tableData = require("./tableData");
const general = require("./general");

const BUILDERS = {
  section_break: sectionBreak,
  executive_summary: executiveSummary,
  comparison: comparison,
  timeline: timeline,
  kpi: kpi,
  table_data: tableData,
  agenda: agenda,
  quote: quote,
  closing: closing,
  general: general,
};

/**
 * Dispatch a slide build to the appropriate archetype builder.
 * Variant is selected by slideIndex % VARIANT_COUNT for automatic visual rotation.
 */
function dispatch(pres, ctx) {
  const builder = BUILDERS[ctx.archetype] || BUILDERS.general;
  const variant = ctx.slideIndex % builder.VARIANT_COUNT;
  builder.build(pres, ctx, variant);
}

module.exports = { dispatch, BUILDERS };
