import unittest

from biomed_workbench.services.compute import container_plan, local_model_plan, slurm_plan


class ComputePlanTests(unittest.TestCase):
    def test_container_plan_is_argument_safe_and_gpu_explicit(self):
        plan = container_plan(
            image="ghcr.io/example/model:1.2.3",
            command=["predict", "--input", "/work/input.fasta"],
            mounts=[{"host": "/tmp/project", "container": "/work", "mode": "rw"}],
            gpu=True,
        )

        self.assertEqual(plan["argv"][:3], ["docker", "run", "--rm"])
        self.assertIn("--gpus", plan["argv"])
        self.assertIn("/tmp/project:/work:rw", plan["argv"])
        self.assertFalse(plan["executes"])

    def test_slurm_plan_quotes_command_and_validates_resources(self):
        plan = slurm_plan(
            command=["python", "run.py", "--name", "sample A"],
            job_name="protein-fold",
            cpus=8,
            memory_gb=32,
            time_minutes=90,
            gpus=1,
        )

        self.assertIn("#SBATCH --cpus-per-task=8", plan["script"])
        self.assertIn("#SBATCH --gres=gpu:1", plan["script"])
        self.assertIn("'sample A'", plan["script"])
        self.assertFalse(plan["submits"])
        with self.assertRaises(ValueError):
            slurm_plan(command=["echo", "x"], job_name="bad;rm", cpus=1, memory_gb=1, time_minutes=1)

    def test_local_model_plan_uses_open_local_backends_without_api_tokens(self):
        boltz = local_model_plan("boltz", {"input": "target.yaml", "output": "results"})
        foldseek = local_model_plan("foldseek", {"query": "query.pdb", "database": "pdb", "output": "hits.tsv"})

        self.assertEqual(boltz["argv"][:2], ["boltz", "predict"])
        self.assertEqual(foldseek["argv"][:2], ["foldseek", "easy-search"])
        self.assertNotIn("api", repr(boltz).lower())
        self.assertFalse(boltz["executes"])
        with self.assertRaises(ValueError):
            local_model_plan("hosted-nim", {})


if __name__ == "__main__":
    unittest.main()
