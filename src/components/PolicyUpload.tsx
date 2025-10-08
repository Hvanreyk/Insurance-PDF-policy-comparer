import { useRef, useState } from 'react';
import { Upload, CheckCircle, AlertCircle } from 'lucide-react';
import { PolicyData } from '../types/policy';
import { parsePolicyPDFViaPython } from '../utils/pythonApiClient';
import EditablePolicyData from './EditablePolicyData';

interface PolicyUploadProps {
  label: string;
  onUpload: (data: PolicyData) => void;
  uploaded: boolean;
  policyData: PolicyData | null;
}

export default function PolicyUpload({
  label,
  onUpload,
  uploaded,
  policyData,
}: PolicyUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (file.type !== 'application/pdf' && !file.name.endsWith('.pdf')) {
      setError('Please upload a PDF file');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await parsePolicyPDFViaPython(file);
      onUpload(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to parse PDF');
    } finally {
      setLoading(false);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border-2 border-dashed border-slate-300 hover:border-blue-400 transition-colors">
      <div className="p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">{label}</h3>

        {!uploaded ? (
          <button
            onClick={handleClick}
            disabled={loading}
            className="w-full py-8 flex flex-col items-center justify-center gap-3 text-slate-600 hover:text-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                <span className="text-sm font-medium">Processing PDF...</span>
              </>
            ) : (
              <>
                <Upload className="w-12 h-12" />
                <span className="text-sm font-medium">
                  Click to upload PDF or drag and drop
                </span>
              </>
            )}
          </button>
        ) : (
          <div className="py-6">
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle className="w-6 h-6 text-green-600" />
              <span className="font-medium text-slate-800">PDF Uploaded</span>
            </div>

            {policyData && (
              <>
                <div className="space-y-2 text-sm mb-4">
                  {policyData.insured && (
                    <div className="flex gap-2">
                      <span className="text-slate-500">Insured:</span>
                      <span className="text-slate-800 font-medium">{policyData.insured}</span>
                    </div>
                  )}
                  {policyData.policy_year && (
                    <div className="flex gap-2">
                      <span className="text-slate-500">Year:</span>
                      <span className="text-slate-800 font-medium">{policyData.policy_year}</span>
                    </div>
                  )}
                  {policyData.period_of_insurance && (
                    <div className="flex gap-2">
                      <span className="text-slate-500">Period:</span>
                      <span className="text-slate-800 font-medium">
                        {policyData.period_of_insurance.from} to {policyData.period_of_insurance.to}
                      </span>
                    </div>
                  )}
                </div>

                <EditablePolicyData
                  data={policyData}
                  label="Extracted Values"
                  onUpdate={onUpload}
                />
              </>
            )}

            <button
              onClick={handleClick}
              className="mt-4 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              Upload different file
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 bg-red-50 border border-red-200 rounded p-3 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>
    </div>
  );
}
