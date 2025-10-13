import { useState } from 'react';
import { ArrowUp, ArrowDown, Minus, Eye, FileText } from 'lucide-react';
import { ClauseMatch } from '../../types/clauseComparison';
import ClauseDetailView from './ClauseDetailView';

interface ClauseMatchResultsProps {
  matches: ClauseMatch[];
}

export default function ClauseMatchResults({ matches }: ClauseMatchResultsProps) {
  const [selectedMatch, setSelectedMatch] = useState<ClauseMatch | null>(null);

  const getStatusBadge = (status: string) => {
    const badges = {
      added: 'bg-green-100 text-green-800 border border-green-300',
      removed: 'bg-red-100 text-red-800 border border-red-300',
      modified: 'bg-amber-100 text-amber-800 border border-amber-300',
      unchanged: 'bg-slate-100 text-slate-800 border border-slate-300',
    };
    return badges[status as keyof typeof badges] || badges.unchanged;
  };

  const getMaterialityBadge = (score: number) => {
    if (score >= 0.7) {
      return 'bg-red-100 text-red-800 border border-red-300';
    } else if (score >= 0.4) {
      return 'bg-amber-100 text-amber-800 border border-amber-300';
    } else {
      return 'bg-green-100 text-green-800 border border-green-300';
    }
  };

  const getStrictnessIcon = (delta: number) => {
    if (delta > 0) return <ArrowUp className="w-4 h-4 text-red-600" />;
    if (delta < 0) return <ArrowDown className="w-4 h-4 text-green-600" />;
    return <Minus className="w-4 h-4 text-slate-600" />;
  };

  const formatPageRef = (evidence: ClauseMatch['evidence']) => {
    const refs: string[] = [];
    if (evidence.a) {
      const pageA =
        evidence.a.page_start === evidence.a.page_end
          ? `p.${evidence.a.page_start}`
          : `p.${evidence.a.page_start}-${evidence.a.page_end}`;
      refs.push(`A: ${pageA}`);
    }
    if (evidence.b) {
      const pageB =
        evidence.b.page_start === evidence.b.page_end
          ? `p.${evidence.b.page_start}`
          : `p.${evidence.b.page_start}-${evidence.b.page_end}`;
      refs.push(`B: ${pageB}`);
    }
    return refs.join(' | ');
  };

  const truncateId = (id: string | null) => {
    if (!id) return 'N/A';
    if (id.length <= 12) return id;
    return `${id.substring(0, 8)}...`;
  };

  if (matches.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-12 text-center">
        <FileText className="w-16 h-16 text-slate-300 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-slate-800 mb-2">No matches found</h3>
        <p className="text-slate-600">
          Try adjusting your filters to see more results.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Clause A ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Clause B ID
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Similarity
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Materiality
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Strictness
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Pages
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {matches.map((match, index) => (
                <tr
                  key={index}
                  className="hover:bg-slate-50 transition-colors"
                >
                  <td className="px-4 py-4">
                    <span
                      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${getStatusBadge(
                        match.status
                      )}`}
                    >
                      {match.status}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <span className="text-sm text-slate-800 font-mono" title={match.a_id || ''}>
                      {truncateId(match.a_id)}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <span className="text-sm text-slate-800 font-mono" title={match.b_id || ''}>
                      {truncateId(match.b_id)}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-center">
                    {match.similarity !== null ? (
                      <div className="flex flex-col items-center">
                        <span className="text-sm font-semibold text-slate-800">
                          {(match.similarity * 100).toFixed(1)}%
                        </span>
                        <div className="w-16 bg-slate-200 rounded-full h-1.5 mt-1">
                          <div
                            className="bg-blue-600 h-1.5 rounded-full"
                            style={{ width: `${match.similarity * 100}%` }}
                          />
                        </div>
                      </div>
                    ) : (
                      <span className="text-sm text-slate-400">N/A</span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-center">
                    <span
                      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${getMaterialityBadge(
                        match.materiality_score
                      )}`}
                    >
                      {match.materiality_score.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-center gap-1">
                      {getStrictnessIcon(match.strictness_delta)}
                      <span className="text-sm font-medium text-slate-700">
                        {match.strictness_delta > 0 ? '+' : ''}
                        {match.strictness_delta}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span className="text-xs text-slate-600">
                      {formatPageRef(match.evidence)}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-center">
                    <button
                      onClick={() => setSelectedMatch(match)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded hover:bg-blue-700 transition-colors"
                    >
                      <Eye className="w-3 h-3" />
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selectedMatch && (
        <ClauseDetailView
          match={selectedMatch}
          onClose={() => setSelectedMatch(null)}
        />
      )}
    </>
  );
}
