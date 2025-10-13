import { X, Copy, CheckCircle2 } from 'lucide-react';
import { ClauseMatch } from '../../types/clauseComparison';
import { useState } from 'react';

interface ClauseDetailViewProps {
  match: ClauseMatch;
  onClose: () => void;
}

export default function ClauseDetailView({ match, onClose }: ClauseDetailViewProps) {
  const [copiedA, setCopiedA] = useState(false);
  const [copiedB, setCopiedB] = useState(false);

  const copyToClipboard = (text: string, isA: boolean) => {
    navigator.clipboard.writeText(text);
    if (isA) {
      setCopiedA(true);
      setTimeout(() => setCopiedA(false), 2000);
    } else {
      setCopiedB(true);
      setTimeout(() => setCopiedB(false), 2000);
    }
  };

  const formatPageRange = (pageStart: number, pageEnd: number) => {
    return pageStart === pageEnd ? `p.${pageStart}` : `p.${pageStart}-${pageEnd}`;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-slate-200">
          <h3 className="text-xl font-semibold text-slate-800">Clause Details</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-slate-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-slate-700">Policy A Clause ID</h4>
                {match.a_id && (
                  <button
                    onClick={() => copyToClipboard(match.a_id!, true)}
                    className="text-slate-500 hover:text-blue-600 transition-colors"
                  >
                    {copiedA ? (
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                )}
              </div>
              <p className="text-sm text-slate-800 font-mono break-all">
                {match.a_id || 'N/A'}
              </p>
              {match.evidence.a && (
                <p className="text-xs text-slate-600 mt-2">
                  {formatPageRange(match.evidence.a.page_start, match.evidence.a.page_end)}
                </p>
              )}
            </div>

            <div className="bg-slate-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-slate-700">Policy B Clause ID</h4>
                {match.b_id && (
                  <button
                    onClick={() => copyToClipboard(match.b_id!, false)}
                    className="text-slate-500 hover:text-blue-600 transition-colors"
                  >
                    {copiedB ? (
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                )}
              </div>
              <p className="text-sm text-slate-800 font-mono break-all">
                {match.b_id || 'N/A'}
              </p>
              {match.evidence.b && (
                <p className="text-xs text-slate-600 mt-2">
                  {formatPageRange(match.evidence.b.page_start, match.evidence.b.page_end)}
                </p>
              )}
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            {match.similarity !== null && (
              <div className="bg-blue-50 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-blue-900 mb-2">Similarity Score</h4>
                <div className="flex items-end gap-2">
                  <p className="text-2xl font-bold text-blue-700">
                    {(match.similarity * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="w-full bg-blue-200 rounded-full h-2 mt-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{ width: `${match.similarity * 100}%` }}
                  />
                </div>
              </div>
            )}

            <div className="bg-amber-50 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-amber-900 mb-2">Materiality Score</h4>
              <p className="text-2xl font-bold text-amber-700">
                {match.materiality_score.toFixed(2)}
              </p>
              <p className="text-xs text-amber-600 mt-1">
                {match.materiality_score >= 0.7
                  ? 'High Impact'
                  : match.materiality_score >= 0.4
                  ? 'Medium Impact'
                  : 'Low Impact'}
              </p>
            </div>

            <div className="bg-slate-50 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-slate-700 mb-2">Strictness Delta</h4>
              <p className="text-2xl font-bold text-slate-800">
                {match.strictness_delta > 0 ? '+' : ''}
                {match.strictness_delta}
              </p>
              <p className="text-xs text-slate-600 mt-1">
                {match.strictness_delta > 0
                  ? 'More Restrictive'
                  : match.strictness_delta < 0
                  ? 'Less Restrictive'
                  : 'No Change'}
              </p>
            </div>
          </div>

          {match.review_required && (
            <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
              <p className="text-sm font-medium text-orange-800">
                Review Required: This clause requires manual review
              </p>
            </div>
          )}

          {match.token_diff && (
            <div className="space-y-4">
              <h4 className="text-sm font-semibold text-slate-800">Token Differences</h4>
              <div className="grid md:grid-cols-2 gap-4">
                {match.token_diff.removed.length > 0 && (
                  <div>
                    <h5 className="text-sm font-medium text-red-700 mb-2">
                      Removed Tokens ({match.token_diff.removed.length})
                    </h5>
                    <div className="flex flex-wrap gap-2">
                      {match.token_diff.removed.map((token, index) => (
                        <span
                          key={index}
                          className="inline-block px-3 py-1 bg-red-100 text-red-800 text-sm rounded-full"
                        >
                          {token}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {match.token_diff.added.length > 0 && (
                  <div>
                    <h5 className="text-sm font-medium text-green-700 mb-2">
                      Added Tokens ({match.token_diff.added.length})
                    </h5>
                    <div className="flex flex-wrap gap-2">
                      {match.token_diff.added.map((token, index) => (
                        <span
                          key={index}
                          className="inline-block px-3 py-1 bg-green-100 text-green-800 text-sm rounded-full"
                        >
                          {token}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {match.numeric_delta && (
            <div>
              <h4 className="text-sm font-semibold text-slate-800 mb-3">Numeric Changes</h4>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-slate-600 mb-1">Field</p>
                    <p className="font-medium text-slate-800">{match.numeric_delta.field}</p>
                  </div>
                  <div>
                    <p className="text-slate-600 mb-1">Policy A</p>
                    <p className="font-medium text-slate-800">
                      {match.numeric_delta.a_value !== null
                        ? match.numeric_delta.a_value.toLocaleString()
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-600 mb-1">Policy B</p>
                    <p className="font-medium text-slate-800">
                      {match.numeric_delta.b_value !== null
                        ? match.numeric_delta.b_value.toLocaleString()
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-600 mb-1">Change</p>
                    <p className="font-medium text-slate-800">
                      {match.numeric_delta.delta_pct !== null
                        ? `${match.numeric_delta.delta_pct > 0 ? '+' : ''}${match.numeric_delta.delta_pct.toFixed(1)}%`
                        : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end p-6 border-t border-slate-200">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
