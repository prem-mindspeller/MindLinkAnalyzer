export function buildNeuroprofileReportDocument(analysisResults) {
  const exportDoc = analysisResults?.neuroprofile_feature_export;

  if (!exportDoc || typeof exportDoc !== 'object' || Array.isArray(exportDoc)) {
    throw new Error('Missing neuroprofile_feature_export in analysis results.');
  }
  if (exportDoc.error) {
    throw new Error(`Neuroprofile export unavailable: ${exportDoc.error}`);
  }

  return JSON.stringify(exportDoc, null, 2);
}
