import { ArrowUp, ArrowDown, Minus, Download, RefreshCw } from 'lucide-react';
import { PolicyData } from '../types/policy';
import { comparePolicies, formatCurrency, formatPercent } from '../utils/comparison';

interface ComparisonViewProps {
  policyA: PolicyData;
  policyB: PolicyData;
  onClear: () => void;
}

export default function ComparisonView({ policyA, policyB, onClear }: ComparisonViewProps) {
  const comparison = comparePolicies(policyA, policyB);

  const handleDownloadJSON = () => {
    const jsonData = {
      policy_a: policyA,
      policy_b: policyB,
      comparison,
    };

    const blob = new Blob([JSON.stringify(jsonData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `policy-comparison-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getChangeColor = (deltaAbs: number | null, isPremium: boolean) => {
    if (deltaAbs === null || deltaAbs === 0) return 'text-slate-600';
    if (isPremium) {
      return deltaAbs > 0 ? 'text-red-600' : 'text-green-600';
    } else {
      return deltaAbs > 0 ? 'text-blue-600' : 'text-orange-600';
    }
  };

  const getChangeIcon = (deltaAbs: number | null) => {
    if (deltaAbs === null || deltaAbs === 0) return <Minus className="w-4 h-4" />;
    if (deltaAbs > 0) return <ArrowUp className="w-4 h-4" />;
    return <ArrowDown className="w-4 h-4" />;
  };

  const isPremiumField = (field: string) => field.toLowerCase().includes('premium');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-slate-800 mb-2">
              Policy Comparison
            </h2>
            <p className="text-slate-600">
              Comparing {policyA.policy_year || 'Year A'} vs {policyB.policy_year || 'Year B'}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleDownloadJSON}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Download className="w-4 h-4" />
              Download JSON
            </button>
            <button
              onClick={onClear}
              className="flex items-center gap-2 px-4 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              New Comparison
            </button>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
        <div className="flex flex-wrap gap-6 text-sm">
          <div className="flex items-center gap-2">
            <ArrowUp className="w-4 h-4 text-red-600" />
            <span className="text-slate-700">Premium increase (red)</span>
          </div>
          <div className="flex items-center gap-2">
            <ArrowUp className="w-4 h-4 text-blue-600" />
            <span className="text-slate-700">Coverage increase (blue)</span>
          </div>
          <div className="flex items-center gap-2">
            <ArrowDown className="w-4 h-4 text-green-600" />
            <span className="text-slate-700">Decrease (green/orange)</span>
          </div>
        </div>
      </div>

      {/* Comparison Table */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-4 text-left text-sm font-semibold text-slate-700">
                  Field
                </th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700">
                  Year A
                </th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700">
                  Year B
                </th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700">
                  Change ($)
                </th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700">
                  Change (%)
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {Object.entries(comparison).map(([field, delta]) => {
                const isPremium = isPremiumField(field);
                const changeColor = getChangeColor(delta.delta_abs, isPremium);

                return (
                  <tr key={field} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 text-sm font-medium text-slate-800">
                      {field}
                    </td>
                    <td className="px-6 py-4 text-sm text-right text-slate-700">
                      {formatCurrency(delta.a)}
                    </td>
                    <td className="px-6 py-4 text-sm text-right text-slate-700">
                      {formatCurrency(delta.b)}
                    </td>
                    <td className={`px-6 py-4 text-sm text-right font-semibold ${changeColor}`}>
                      <div className="flex items-center justify-end gap-2">
                        {getChangeIcon(delta.delta_abs)}
                        {delta.delta_abs !== null
                          ? formatCurrency(Math.abs(delta.delta_abs))
                          : 'N/A'}
                      </div>
                    </td>
                    <td className={`px-6 py-4 text-sm text-right font-semibold ${changeColor}`}>
                      {formatPercent(delta.delta_pct)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* JSON View (Collapsible) */}
      <details className="bg-white rounded-lg shadow-sm border border-slate-200">
        <summary className="px-6 py-4 cursor-pointer font-semibold text-slate-800 hover:bg-slate-50 transition-colors">
          View Raw JSON Data
        </summary>
        <div className="px-6 pb-6">
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-700 mb-2">Policy A</h4>
              <pre className="bg-slate-50 p-4 rounded text-xs overflow-auto max-h-96">
                {JSON.stringify(policyA, null, 2)}
              </pre>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-700 mb-2">Policy B</h4>
              <pre className="bg-slate-50 p-4 rounded text-xs overflow-auto max-h-96">
                {JSON.stringify(policyB, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      </details>

      {/* Future Features Notice */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 mb-2">Coming Soon</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• PDF report generation with detailed comparisons</li>
          <li>• Wording and clause comparison</li>
          <li>• Historical trend analysis across multiple years</li>
        </ul>
      </div>
    </div>
  );
}
