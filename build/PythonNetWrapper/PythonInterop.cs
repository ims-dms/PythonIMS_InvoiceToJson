using Python.Runtime;
using System;

namespace PythonNetWrapper
{
    public class PythonInterop : IDisposable
    {
        private bool _isInitialized;

        public PythonInterop()
        {
            InitializePython();
        }

        private void InitializePython()
        {
            if (!_isInitialized)
            {
                PythonEngine.Initialize();
                _isInitialized = true;
            }
        }

        public void Dispose()
        {
            if (_isInitialized)
            {
                PythonEngine.Shutdown();
                _isInitialized = false;
            }
        }

        public string CallProcessInvoice(string filePath, string companyID, string username, string licenceID, string connectionParamsJson)
        {
            using (Py.GIL())
            {
                dynamic sys = Py.Import("sys");
                // Optionally add your python app directory to sys.path
                sys.path.append("e:/Development/FinalPython");

                dynamic api = Py.Import("api");

                // Prepare arguments for the process_invoice function
                // Since process_invoice is an async FastAPI endpoint, we need to call the underlying logic differently.
                // For demonstration, assume you have a synchronous function in api.py to call here.
                // You may need to refactor api.py to expose a synchronous function for this purpose.

                // Example: call a synchronous function 'process_invoice_sync' in api.py
                // dynamic result = api.process_invoice_sync(filePath, companyID, username, licenceID, connectionParamsJson);

                // For now, just return a placeholder string
                return "Interop call placeholder - implement synchronous Python function to call";
            }
        }
    }
}
