import { useState } from 'react';
import { PolicyData } from '../types/policy';
import { Edit2, Check, X } from 'lucide-react';

interface EditablePolicyDataProps {
  data: PolicyData;
  label: string;
  onUpdate: (data: PolicyData) => void;
}

export default function EditablePolicyData({ data, label, onUpdate }: EditablePolicyDataProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editData, setEditData] = useState(data);

  const handleSave = () => {
    onUpdate(editData);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditData(data);
    setIsEditing(false);
  };

  const updateField = (path: string[], value: string) => {
    const newData = { ...editData };
    let current: any = newData;

    for (let i = 0; i < path.length - 1; i++) {
      current = current[path[i]];
    }

    const lastKey = path[path.length - 1];
    const numValue = parseFloat(value.replace(/[^0-9.]/g, ''));
    current[lastKey] = isNaN(numValue) ? undefined : numValue;

    setEditData(newData);
  };

  if (!isEditing) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-800">{label}</h3>
          <button
            onClick={() => setIsEditing(true)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-100 text-slate-700 rounded hover:bg-slate-200 transition-colors"
          >
            <Edit2 className="w-4 h-4" />
            Edit Values
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div className="flex gap-2">
            <span className="text-slate-500 w-40">Contents:</span>
            <span className="text-slate-800 font-medium">
              {data.sums_insured.contents ? `$${data.sums_insured.contents.toLocaleString()}` : 'N/A'}
            </span>
          </div>
          <div className="flex gap-2">
            <span className="text-slate-500 w-40">Theft (Contents & Stock):</span>
            <span className="text-slate-800 font-medium">
              {data.sums_insured.theft_total ? `$${data.sums_insured.theft_total.toLocaleString()}` : 'N/A'}
            </span>
          </div>
          <div className="flex gap-2">
            <span className="text-slate-500 w-40">BI Turnover:</span>
            <span className="text-slate-800 font-medium">
              {data.sums_insured.bi_turnover ? `$${data.sums_insured.bi_turnover.toLocaleString()}` : 'N/A'}
            </span>
          </div>
          <div className="flex gap-2">
            <span className="text-slate-500 w-40">Public Liability:</span>
            <span className="text-slate-800 font-medium">
              {data.sums_insured.public_liability ? `$${data.sums_insured.public_liability.toLocaleString()}` : 'N/A'}
            </span>
          </div>
          <div className="flex gap-2">
            <span className="text-slate-500 w-40">Total Premium:</span>
            <span className="text-slate-800 font-medium">
              {data.premium.total ? `$${data.premium.total.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-blue-300 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-800">{label} - Editing</h3>
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
          >
            <Check className="w-4 h-4" />
            Save
          </button>
          <button
            onClick={handleCancel}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-slate-200 text-slate-700 rounded hover:bg-slate-300 transition-colors"
          >
            <X className="w-4 h-4" />
            Cancel
          </button>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex gap-2 items-center">
          <label className="text-slate-600 text-sm w-40">Contents:</label>
          <input
            type="text"
            value={editData.sums_insured.contents || ''}
            onChange={(e) => updateField(['sums_insured', 'contents'], e.target.value)}
            className="flex-1 px-3 py-1.5 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder="e.g., 578462"
          />
        </div>

        <div className="flex gap-2 items-center">
          <label className="text-slate-600 text-sm w-40">Theft (Contents & Stock):</label>
          <input
            type="text"
            value={editData.sums_insured.theft_total || ''}
            onChange={(e) => updateField(['sums_insured', 'theft_total'], e.target.value)}
            className="flex-1 px-3 py-1.5 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder="e.g., 70000"
          />
        </div>

        <div className="flex gap-2 items-center">
          <label className="text-slate-600 text-sm w-40">BI Turnover:</label>
          <input
            type="text"
            value={editData.sums_insured.bi_turnover || ''}
            onChange={(e) => updateField(['sums_insured', 'bi_turnover'], e.target.value)}
            className="flex-1 px-3 py-1.5 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder="e.g., 1950000"
          />
        </div>

        <div className="flex gap-2 items-center">
          <label className="text-slate-600 text-sm w-40">Public Liability:</label>
          <input
            type="text"
            value={editData.sums_insured.public_liability || ''}
            onChange={(e) => updateField(['sums_insured', 'public_liability'], e.target.value)}
            className="flex-1 px-3 py-1.5 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder="e.g., 10000000"
          />
        </div>

        <div className="flex gap-2 items-center">
          <label className="text-slate-600 text-sm w-40">Total Premium:</label>
          <input
            type="text"
            value={editData.premium.total || ''}
            onChange={(e) => updateField(['premium', 'total'], e.target.value)}
            className="flex-1 px-3 py-1.5 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder="e.g., 4031.37"
          />
        </div>
      </div>

      <p className="text-xs text-slate-500 mt-4">
        Tip: Enter numbers without commas or dollar signs. They'll be formatted automatically.
      </p>
    </div>
  );
}
