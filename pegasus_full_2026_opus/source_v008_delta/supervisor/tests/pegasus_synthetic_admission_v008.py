"""Admissão SINTÉTICA — exclusiva para qualificação isolada do caminho supervisionado.

Vive sob `supervisor/tests/` (fora do caminho de produção) e é usável apenas via
`--admission` de `run-b/-c/-full`. Prova que `cmd_run` percorre, após uma admissão que
devolve plano, o caminho executável supervisionado completo (W04 armado antes do filho,
Job, SAFE_STOP, retomada, porta de conclusão), usando o `synthetic_chain.py` do pacote —
que roda a via real de worker/commit/journal/lease W04, mas recusa dados reais
(`SYNTHETIC_MARKER_REQUIRED`, saída fora do pacote selado).

NUNCA produz plano econômico: `make_run_plan` recusaria `economic=True` sem prova de
autorização externa, e esta admissão só emite `economic=False` apontando para o
`synthetic_chain.py`. Não aponta, e não pode promover, o executor econômico real.

Parametrização por variáveis de ambiente (apenas o arranjo sintético; nada produtivo):
  PEGASUS_SYN_INPUTS   diretório de fixtures sintéticas (SYNTHETIC_ONLY.json presente)
  PEGASUS_SYN_OUT      raiz de saída nova, fora do pacote
  PEGASUS_SYN_WORKERS  nº de workers (default 3)
  PEGASUS_SYN_STOP     se '1', injeta SAFE_STOP após o 1º commit (prova de parada)
  PEGASUS_SYN_TRY_ECONOMIC  se '1', tenta (e deve falhar) marcar o plano como econômico
  PEGASUS_SYN_TARGET_ECONOMIC_ENTRY  se '1', aponta argv ao executor econômico real
  PEGASUS_SYN_RAISE    se '1', a admissão levanta exceção técnica (classificação => exit 3)
  PEGASUS_SYN_CHILD_EXIT  se definido (int), o filho supervisionado é um processo trivial que
                       sai com esse código (classificação de filho falho => exit 3)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUP = HERE.parent
if str(SUP) not in sys.path:
    sys.path.insert(0, str(SUP))
import pegasus_supervisor_v008 as sup


class SyntheticAdmission:
    schema = "PEGASUS_FULL_2026_V008_SYNTHETIC_ADMISSION_ISOLATED_NON_ECONOMIC"

    def admit(self, *, phase, package_root, entry, ns):
        if os.environ.get("PEGASUS_SYN_RAISE") == "1":
            raise RuntimeError("SYNTHETIC_ADMISSION_TECHNICAL_FAILURE")
        inputs = Path(os.environ["PEGASUS_SYN_INPUTS"]).resolve()
        out = Path(os.environ["PEGASUS_SYN_OUT"]).resolve()
        workers = int(os.environ.get("PEGASUS_SYN_WORKERS", "3"))
        if not (inputs / "SYNTHETIC_ONLY.json").is_file():
            raise entry.Blocked("SYNTHETIC_MARKER_ABSENT")
        if out.resolve().is_relative_to(Path(package_root).resolve()):
            raise entry.Blocked("SYNTHETIC_OUTPUT_INSIDE_PACKAGE_FORBIDDEN")
        chain = Path(package_root) / "tests" / "synthetic_chain.py"
        argv = [sys.executable, "-B", str(chain), "--inputs", str(inputs), "--out", str(out),
                "--workers", str(workers)]
        if os.environ.get("PEGASUS_SYN_TARGET_ECONOMIC_ENTRY") == "1":
            # Negativo: apontar o executor econômico real. make_run_plan permite emitir o
            # plano só como econômico; sem prova externa, make_run_plan recusa de imediato.
            argv = [sys.executable, "-I", "-B", str(Path(package_root) / "CODE" / "pegasus_entry.py"), "run-b"]
            return sup.make_run_plan(label="SYN_ECONOMIC_ENTRY", argv=argv, protected_root=inputs,
                                     out_root=out, economic=True, external_authorization_proven=False,
                                     admission_schema=self.schema, admission_sha256=getattr(self, "injected_sha256", ""))
        child_exit = os.environ.get("PEGASUS_SYN_CHILD_EXIT")
        if child_exit is not None:
            argv = [sys.executable, "-I", "-c", "import sys; sys.exit(%d)" % int(child_exit)]
            out.mkdir(parents=True, exist_ok=True)
            return sup.make_run_plan(label="SYN_CHILD_EXIT", argv=argv, protected_root=inputs, out_root=out,
                                     economic=False, admission_schema=self.schema,
                                     admission_sha256=getattr(self, "injected_sha256", ""), timeout_s=300.0)
        economic = os.environ.get("PEGASUS_SYN_TRY_ECONOMIC") == "1"
        stop_after = 1 if os.environ.get("PEGASUS_SYN_STOP") == "1" else None
        return sup.make_run_plan(label="SYN_SUPERVISED", argv=argv, protected_root=inputs, out_root=out,
                                 economic=economic, external_authorization_proven=False,
                                 admission_schema=self.schema,
                                 admission_sha256=getattr(self, "injected_sha256", ""),
                                 stop_after_committed=stop_after, timeout_s=1800.0)


ADMISSION = SyntheticAdmission()
