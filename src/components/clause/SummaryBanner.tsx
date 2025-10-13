import { Plus, Minus, Edit, CheckCircle } from 'lucide-react';
import { Summary } from '../../types/clauseComparison';

interface SummaryBannerProps {
  summary: Summary;
}

export default function SummaryBanner({ summary }: SummaryBannerProps) {
  const { counts, bullets } = summary;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-green-50 to-green-100 border border-green-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="bg-green-600 text-white rounded-lg p-2">
              <Plus className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-green-900">{counts.added}</p>
              <p className="text-sm text-green-700 font-medium">Added</p>
            </div>
          </div>
        </div>

        <div className="bg-gradient-to-br from-red-50 to-red-100 border border-red-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="bg-red-600 text-white rounded-lg p-2">
              <Minus className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-red-900">{counts.removed}</p>
              <p className="text-sm text-red-700 font-medium">Removed</p>
            </div>
          </div>
        </div>

        <div className="bg-gradient-to-br from-amber-50 to-amber-100 border border-amber-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="bg-amber-600 text-white rounded-lg p-2">
              <Edit className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-amber-900">{counts.modified}</p>
              <p className="text-sm text-amber-700 font-medium">Modified</p>
            </div>
          </div>
        </div>

        <div className="bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="bg-slate-600 text-white rounded-lg p-2">
              <CheckCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{counts.unchanged}</p>
              <p className="text-sm text-slate-700 font-medium">Unchanged</p>
            </div>
          </div>
        </div>
      </div>

      {bullets.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4">Summary Highlights</h3>
          <ul className="space-y-2">
            {bullets.map((bullet, index) => {
              const isAdded = bullet.toLowerCase().includes('added');
              const isRemoved = bullet.toLowerCase().includes('removed');
              const isModified = bullet.toLowerCase().includes('modified');

              let bulletColor = 'text-slate-700';
              let bulletIcon = '•';
              if (isAdded) {
                bulletColor = 'text-green-700';
                bulletIcon = '+';
              } else if (isRemoved) {
                bulletColor = 'text-red-700';
                bulletIcon = '−';
              } else if (isModified) {
                bulletColor = 'text-amber-700';
                bulletIcon = '~';
              }

              return (
                <li key={index} className={`flex gap-3 text-sm ${bulletColor}`}>
                  <span className="font-bold flex-shrink-0 w-4">{bulletIcon}</span>
                  <span>{bullet}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
