import { useRef } from 'react';
import { Upload, FileText, X } from 'lucide-react';

interface ClauseComparerUploadProps {
  fileA: File | null;
  fileB: File | null;
  onFileASelect: (file: File) => void;
  onFileBSelect: (file: File) => void;
  onClear: () => void;
}

export default function ClauseComparerUpload({
  fileA,
  fileB,
  onFileASelect,
  onFileBSelect,
  onClear,
}: ClauseComparerUploadProps) {
  const fileAInputRef = useRef<HTMLInputElement>(null);
  const fileBInputRef = useRef<HTMLInputElement>(null);

  const handleFileAChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && (file.type === 'application/pdf' || file.name.endsWith('.pdf'))) {
      onFileASelect(file);
    }
  };

  const handleFileBChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && (file.type === 'application/pdf' || file.name.endsWith('.pdf'))) {
      onFileBSelect(file);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-sm border-2 border-dashed border-slate-300 hover:border-blue-400 transition-colors">
          <div className="p-6">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">
              Policy A - Expiring Policy
            </h3>

            {!fileA ? (
              <button
                onClick={() => fileAInputRef.current?.click()}
                className="w-full py-12 flex flex-col items-center justify-center gap-3 text-slate-600 hover:text-blue-600 transition-colors"
              >
                <Upload className="w-12 h-12" />
                <span className="text-sm font-medium">Click to upload PDF</span>
                <span className="text-xs text-slate-500">or drag and drop</span>
              </button>
            ) : (
              <div className="py-6">
                <div className="flex items-start gap-3 bg-slate-50 p-4 rounded-lg">
                  <FileText className="w-8 h-8 text-blue-600 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {fileA.name}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      {formatFileSize(fileA.size)}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      onClear();
                      if (fileAInputRef.current) fileAInputRef.current.value = '';
                    }}
                    className="flex-shrink-0 text-slate-400 hover:text-red-600 transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <button
                  onClick={() => fileAInputRef.current?.click()}
                  className="mt-4 text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  Choose different file
                </button>
              </div>
            )}

            <input
              ref={fileAInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileAChange}
              className="hidden"
            />
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border-2 border-dashed border-slate-300 hover:border-blue-400 transition-colors">
          <div className="p-6">
            <h3 className="text-lg font-semibold text-slate-800 mb-4">
              Policy B - New Quote
            </h3>

            {!fileB ? (
              <button
                onClick={() => fileBInputRef.current?.click()}
                className="w-full py-12 flex flex-col items-center justify-center gap-3 text-slate-600 hover:text-blue-600 transition-colors"
              >
                <Upload className="w-12 h-12" />
                <span className="text-sm font-medium">Click to upload PDF</span>
                <span className="text-xs text-slate-500">or drag and drop</span>
              </button>
            ) : (
              <div className="py-6">
                <div className="flex items-start gap-3 bg-slate-50 p-4 rounded-lg">
                  <FileText className="w-8 h-8 text-blue-600 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {fileB.name}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      {formatFileSize(fileB.size)}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      onClear();
                      if (fileBInputRef.current) fileBInputRef.current.value = '';
                    }}
                    className="flex-shrink-0 text-slate-400 hover:text-red-600 transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <button
                  onClick={() => fileBInputRef.current?.click()}
                  className="mt-4 text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  Choose different file
                </button>
              </div>
            )}

            <input
              ref={fileBInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileBChange}
              className="hidden"
            />
          </div>
        </div>
      </div>

      {fileA && fileB && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800">
            Both documents are ready. Click the <strong>Run Universal Clause Comparer</strong> button below to start the analysis.
          </p>
        </div>
      )}
    </div>
  );
}
