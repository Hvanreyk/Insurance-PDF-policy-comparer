import { useState } from 'react';
import { FileText, AlertCircle } from 'lucide-react';
import PolicyUpload from './components/PolicyUpload';
import ComparisonView from './components/ComparisonView';
import PolicyWordingComparator from './components/PolicyWordingComparator';
import { PolicyData } from './types/policy';

type TabType = 'numeric' | 'wording';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('numeric');
  const [policyA, setPolicyA] = useState<PolicyData | null>(null);
  const [policyB, setPolicyB] = useState<PolicyData | null>(null);
  const [error, setError] = useState<string>('');

  const handlePolicyAUpload = (data: PolicyData) => {
    setPolicyA(data);
    setError('');
  };

  const handlePolicyBUpload = (data: PolicyData) => {
    setPolicyB(data);
    setError('');
  };

  const clearAll = () => {
    setPolicyA(null);
    setPolicyB(null);
    setError('');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <FileText className="w-10 h-10 text-blue-600" />
            <h1 className="text-4xl font-bold text-slate-800">
              Insurance Policy Comparison Tool
            </h1>
          </div>
          <p className="text-slate-600 text-lg">
            {activeTab === 'numeric'
              ? 'Compare two versions of the same policy and see key dollar amounts side-by-side'
              : 'Analyze clause-level differences between policy documents'}
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="mb-8">
          <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-1 inline-flex gap-1">
            <button
              onClick={() => setActiveTab('numeric')}
              className={`px-6 py-3 rounded-md text-sm font-semibold transition-all ${
                activeTab === 'numeric'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-800 hover:bg-slate-50'
              }`}
            >
              Numeric Comparison
            </button>
            <button
              onClick={() => setActiveTab('wording')}
              className={`px-6 py-3 rounded-md text-sm font-semibold transition-all ${
                activeTab === 'wording'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-800 hover:bg-slate-50'
              }`}
            >
              Wording Document Comparator
            </button>
          </div>
        </div>

        {/* Numeric Comparison Tab */}
        {activeTab === 'numeric' && (
          <>
            {error && (
              <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-red-900 mb-1">Error</h3>
                  <p className="text-red-700">{error}</p>
                </div>
              </div>
            )}

            {/* Upload Section */}
            {(!policyA || !policyB) && (
              <div className="grid md:grid-cols-2 gap-6 mb-8">
                <PolicyUpload
                  label="Policy Year A (Older)"
                  onUpload={handlePolicyAUpload}
                  uploaded={!!policyA}
                  policyData={policyA}
                />
                <PolicyUpload
                  label="Policy Year B (Newer)"
                  onUpload={handlePolicyBUpload}
                  uploaded={!!policyB}
                  policyData={policyB}
                />
              </div>
            )}

            {/* Comparison View */}
            {policyA && policyB && (
              <ComparisonView
                policyA={policyA}
                policyB={policyB}
                onClear={clearAll}
              />
            )}

            {/* Instructions */}
            {!policyA && !policyB && (
              <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 mt-8">
                <h2 className="text-xl font-semibold text-slate-800 mb-4">
                  How to Use This Tool
                </h2>
                <ol className="space-y-3 text-slate-700">
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                      1
                    </span>
                    <span>Upload the older policy version (Year A) in the left panel</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                      2
                    </span>
                    <span>Upload the newer policy version (Year B) in the right panel</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                      3
                    </span>
                    <span>
                      View the side-by-side comparison with highlighted increases and decreases
                    </span>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                      4
                    </span>
                    <span>Download the comparison data as JSON for further analysis</span>
                  </li>
                </ol>
              </div>
            )}
          </>
        )}

        {/* Wording Document Comparator Tab */}
        {activeTab === 'wording' && <PolicyWordingComparator />}
      </div>
    </div>
  );
}

export default App;
