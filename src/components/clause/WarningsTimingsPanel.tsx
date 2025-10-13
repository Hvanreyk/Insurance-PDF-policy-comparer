import { useState } from 'react';
import { AlertTriangle, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { Timings } from '../../types/clauseComparison';

interface WarningsTimingsPanelProps {
  warnings: string[];
  timings: Timings;
}

export default function WarningsTimingsPanel({ warnings, timings }: WarningsTimingsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const formatTime = (ms: number): string => {
    return `${ms.toFixed(2)} ms`;
  };

  const getRelativeWidth = (value: number, max: number): number => {
    return (value / max) * 100;
  };

  const maxTiming = Math.max(
    timings.parse_a,
    timings.parse_b,
    timings.align,
    timings.diff
  );

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-slate-600" />
          <h3 className="text-lg font-semibold text-slate-800">
            Performance & Warnings
          </h3>
          {warnings.length > 0 && (
            <span className="bg-orange-100 text-orange-800 text-xs font-bold px-2 py-1 rounded-full">
              {warnings.length}
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-slate-600" />
        ) : (
          <ChevronDown className="w-5 h-5 text-slate-600" />
        )}
      </button>

      {isExpanded && (
        <div className="p-4 border-t border-slate-200 space-y-6">
          {warnings.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-orange-600" />
                Warnings
              </h4>
              <div className="space-y-2">
                {warnings.map((warning, index) => (
                  <div
                    key={index}
                    className="bg-orange-50 border border-orange-200 rounded-lg p-3 flex items-start gap-2"
                  >
                    <AlertTriangle className="w-4 h-4 text-orange-600 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-orange-800">{warning}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <h4 className="text-sm font-semibold text-slate-700 mb-3">Processing Times</h4>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-700">Parse Policy A</span>
                  <span className="text-sm font-semibold text-slate-800">
                    {formatTime(timings.parse_a)}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{ width: `${getRelativeWidth(timings.parse_a, maxTiming)}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-700">Parse Policy B</span>
                  <span className="text-sm font-semibold text-slate-800">
                    {formatTime(timings.parse_b)}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{ width: `${getRelativeWidth(timings.parse_b, maxTiming)}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-700">Alignment</span>
                  <span className="text-sm font-semibold text-slate-800">
                    {formatTime(timings.align)}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full transition-all"
                    style={{ width: `${getRelativeWidth(timings.align, maxTiming)}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-700">Diffing</span>
                  <span className="text-sm font-semibold text-slate-800">
                    {formatTime(timings.diff)}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full transition-all"
                    style={{ width: `${getRelativeWidth(timings.diff, maxTiming)}%` }}
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-800">Total Time</span>
                  <span className="text-lg font-bold text-blue-700">
                    {formatTime(timings.total)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
