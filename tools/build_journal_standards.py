#!/usr/bin/env python3
"""Build the reviewed, versioned journal-standard catalog.

The catalog deliberately distinguishes exact journal rules from publisher-wide
guidance and from fields that the publisher does not state publicly. Unknown
limits remain null and become manual submission checks; they are never filled
from convention or memory.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "biomed_workbench" / "knowledge" / "journal_standards"
METRICS_PATH = OUT_ROOT / "sources" / "jcr-2026-secondary-selected.tsv"
VERSION = "2026.08.03"
REVIEWED_ON = "2026-08-03"


FAMILY_RULES = {
    "nature": {
        "official_sources": [
            "https://www.nature.com/nature/for-authors/formatting-guide",
            "https://www.nature.com/nature/for-authors/initial-submission",
            "https://research-figure-guide.nature.com/",
        ],
        "language_style": [
            "Write for researchers beyond the immediate specialty and define field-specific terms.",
            "Lead with the biological question and advance; separate observation from mechanism and inference.",
            "Use restrained causal language and report biological replication, uncertainty, and statistical tests.",
        ],
        "figure_rules": [
            "Design at final single- or double-column size and keep text legible after reduction.",
            "Use scale bars rather than magnification, consistent labels, editable vector text, and source data.",
        ],
        "reporting_requirements": [
            "Nature Portfolio reporting summary where applicable",
            "data availability statement",
            "code availability statement when custom code is central",
            "study-design-specific reporting guideline",
        ],
        "default_constraints": {
            "main_text_words": None,
            "abstract_words": None,
            "display_items": None,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": [],
        "constraint_status": "journal-specific content page controls; null means no verified public number",
        "required_sections": ["Abstract", "Introduction", "Results", "Discussion", "Methods", "Data availability"],
    },
    "science": {
        "official_sources": [
            "https://www.science.org/content/page/instructions-preparing-initial-manuscript",
            "https://www.science.org/content/page/science-information-authors",
        ],
        "language_style": [
            "Frame broad conceptual importance for a multidisciplinary scientific readership.",
            "Keep the main narrative compact and move necessary technical depth to clearly linked methods or supplements.",
            "State uncertainty and distinguish association, mechanism, and generalization.",
        ],
        "figure_rules": [
            "Figures must remain interpretable at publication size with concise legends and accessible color.",
            "Every display item must carry a distinct part of the argument and trace to source data.",
        ],
        "reporting_requirements": [
            "data and materials availability",
            "code availability where relevant",
            "study-design-specific reporting guideline",
        ],
        "default_constraints": {
            "main_text_words": None,
            "abstract_words": None,
            "display_items": None,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": [],
        "constraint_status": "current article type and official AAAS instructions must be bound at drafting time",
        "required_sections": ["Abstract", "Main text", "References", "Acknowledgments", "Supplementary materials"],
    },
    "cell_press": {
        "official_sources": [
            "https://crosstalk.cell.com/blog/taking-the-references-out-of-the-equation",
            "https://crosstalk.cell.com/hubfs/Files/GA_guide.pdf",
            "https://www.cell.com/star-methods",
        ],
        "language_style": [
            "Build a mechanistic, figure-led story in which each result resolves a stated question.",
            "Use a concise summary and significance framing appropriate to the journal's readership.",
            "Keep procedures reproducible in STAR Methods and avoid repeating methods in Results.",
        ],
        "figure_rules": [
            "Use a single-panel graphical abstract only where the target journal requests it.",
            "Graphical abstracts should be simple, legible, and conceptual rather than a dense data figure.",
            "Bind every result figure to STAR Methods, key resources, source data, and statistical definitions.",
        ],
        "reporting_requirements": [
            "STAR Methods",
            "Key Resources Table",
            "resource availability",
            "data and code availability",
            "study-design-specific reporting guideline",
        ],
        "default_constraints": {
            "main_text_characters_with_spaces": None,
            "main_text_words": None,
            "abstract_words": None,
            "display_items": None,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": [],
        "constraint_status": "Cell Press materials describe common full-length conventions, but the exact journal and article-type page controls all numerical limits",
        "required_sections": [
            "Summary",
            "Introduction",
            "Results",
            "Discussion",
            "Limitations of the study",
            "STAR Methods",
            "Resource availability",
        ],
    },
    "lancet": {
        "official_sources": [
            "https://www.thelancet.com/for-authors",
            "https://www.thelancet.com/pb-assets/Lancet/authors/tl-info-for-authors.pdf",
        ],
        "language_style": [
            "Write for clinicians, researchers, policy makers, and global health readers.",
            "Prioritize clinical importance, absolute effects, uncertainty, harms, and applicability.",
            "Use calibrated interpretation that follows the prespecified design and reporting guideline.",
        ],
        "figure_rules": [
            "Keep the main display set clinically interpretable and move nonessential diagnostics to the appendix.",
            "Show denominators, units, uncertainty, and patient flow where applicable.",
        ],
        "reporting_requirements": [
            "Research in context panel",
            "study-design-specific reporting guideline and checklist",
            "trial registration or protocol where applicable",
            "data sharing statement",
            "role of the funding source",
        ],
        "default_constraints": {
            "main_text_words": None,
            "abstract_words": None,
            "display_items": None,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": [],
        "constraint_status": "bind the current journal PDF and article type before drafting",
        "required_sections": [
            "Structured summary",
            "Introduction",
            "Methods",
            "Results",
            "Discussion",
            "Research in context",
            "Data sharing",
        ],
    },
    "jama": {
        "official_sources": [
            "https://jamanetwork.com/journals/jama/pages/instructions-for-authors",
        ],
        "language_style": [
            "Write direct clinical prose centered on the research question, effect estimates, and uncertainty.",
            "Avoid causal wording beyond the design and discuss clinical meaning separately from statistical significance.",
        ],
        "figure_rules": [
            "Use no more display items than the selected article type permits.",
            "Provide patient flow, denominators, units, confidence intervals, and accessible legends.",
        ],
        "reporting_requirements": [
            "Key Points",
            "study-design-specific reporting guideline",
            "trial registration where applicable",
            "data sharing statement",
        ],
        "default_constraints": {
            "main_text_words": 3000,
            "abstract_words": 350,
            "display_items": 5,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": ["main_text_words", "abstract_words", "display_items"],
        "constraint_status": "JAMA Original Investigation; another article type requires another profile",
        "required_sections": ["Key Points", "Structured Abstract", "Introduction", "Methods", "Results", "Discussion"],
    },
    "nejm": {
        "official_sources": [
            "https://www.nejm.org/author-center/article-types",
            "https://www.nejm.org/author-center/new-manuscripts",
        ],
        "language_style": [
            "Present clinically consequential evidence in compact, transparent prose.",
            "Report absolute and relative effects, adverse events, confidence intervals, and prespecified analyses.",
        ],
        "figure_rules": [
            "Use clinically interpretable tables and figures with complete denominators and uncertainty.",
            "Separate exploratory analyses from prespecified primary and secondary outcomes.",
        ],
        "reporting_requirements": [
            "study-design-specific reporting guideline",
            "trial registration and protocol where applicable",
            "data sharing statement",
        ],
        "default_constraints": {
            "main_text_words": None,
            "abstract_words": 250,
            "display_items": None,
            "references": 40,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": ["abstract_words", "references"],
        "constraint_status": "verified public Original Article abstract and reference limits; other fields require live check",
        "required_sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion"],
    },
    "bmj": {
        "official_sources": ["https://www.bmj.com/about-bmj/resources-authors/article-types"],
        "language_style": [
            "Write for clinicians and decision makers, emphasizing what the study adds and how results affect practice or policy.",
            "Use clear, active prose and a structured discussion that separates strengths, limitations, and implications.",
        ],
        "figure_rules": [
            "Choose display items for clinical comprehension rather than decorative completeness.",
            "Show denominators, uncertainty, participant flow, and clinically meaningful scales.",
        ],
        "reporting_requirements": [
            "What is already known / What this study adds",
            "study-design-specific reporting guideline",
            "patient and public involvement statement where applicable",
            "data sharing statement",
        ],
        "default_constraints": {
            "main_text_words": None,
            "abstract_words": 300,
            "display_items": None,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": ["abstract_words"],
        "constraint_status": "BMJ reports no fixed research word limit; abstract is normally 250-300 words",
        "required_sections": ["Structured Abstract", "Introduction", "Methods", "Results", "Discussion"],
    },
    "general_biology": {
        "official_sources": [],
        "language_style": [
            "Write a question-led, evidence-proportional narrative for the journal's declared biological audience.",
            "Separate discovery, validation, mechanism, and generalization.",
        ],
        "figure_rules": [
            "Every display item must support a named claim and remain readable at final size.",
            "Provide source data, units, biological n, uncertainty, and exact statistical procedures.",
        ],
        "reporting_requirements": [
            "data availability statement",
            "code availability statement where relevant",
            "study-design-specific reporting guideline",
        ],
        "default_constraints": {
            "main_text_words": None,
            "abstract_words": None,
            "display_items": None,
            "references": None,
            "figure_count": None,
            "table_count": None,
        },
        "exact_default_fields": [],
        "constraint_status": "journal-specific official guide controls all numerical limits",
        "required_sections": ["Abstract", "Introduction", "Results", "Discussion", "Methods", "Data availability"],
    },
}


# id, title, family, audience, favored article types, topic keywords, official scope/content source, exact overrides
JOURNALS = [
    ("nature", "Nature", "nature", "A multidisciplinary scientific readership seeking advances of exceptional conceptual reach.", ["Article", "Letter", "Review", "Perspective"], ["multidisciplinary", "mechanism", "conceptual advance", "biology", "medicine"], "https://www.nature.com/nature/for-authors/formatting-guide", {"main_text_words": 4300, "abstract_words": 200, "display_items": 6, "references": 50}),
    ("nature-medicine", "Nature Medicine", "nature", "Biomedical scientists and clinicians interested in disease mechanism, diagnostics, therapeutics, and population impact.", ["Article", "Brief Communication", "Resource", "Review"], ["translational", "clinical", "disease mechanism", "therapeutics", "biomarker"], "https://www.nature.com/nm/content", {"main_text_words": 4000, "abstract_words": 150, "display_items": 6, "references": 60}),
    ("nature-biotechnology", "Nature Biotechnology", "nature", "Biotechnology researchers, engineers, translational scientists, and technology developers.", ["Article", "Brief Communication", "Analysis", "Resource"], ["biotechnology", "technology", "engineering", "therapeutics", "platform"], "https://www.nature.com/nbt/content", {"main_text_words": 3000, "abstract_words": 150, "display_items": 6, "references": 50}),
    ("nature-genetics", "Nature Genetics", "nature", "Geneticists and genomic scientists studying inherited variation, function, disease, and population genetics.", ["Article", "Brief Communication", "Analysis", "Resource"], ["genetics", "genomics", "human genetics", "functional genomics", "population"], "https://www.nature.com/ng/content", {"main_text_words": 4000, "abstract_words": 150, "display_items": 8, "references": 50}),
    ("nature-methods", "Nature Methods", "nature", "Researchers seeking broadly useful experimental and computational methods with rigorous benchmarking.", ["Article", "Brief Communication", "Analysis", "Resource"], ["methods", "benchmark", "technology", "software", "measurement"], "https://www.nature.com/nmeth/content", {"main_text_words": 3000, "abstract_words": 150, "display_items": 6, "references": 50}),
    ("nature-neuroscience", "Nature Neuroscience", "nature", "Neuroscientists spanning molecules, circuits, cognition, behavior, and neurological disease.", ["Article", "Brief Communication", "Resource", "Review"], ["neuroscience", "brain", "circuit", "behavior", "neurological disease"], "https://www.nature.com/neuro/content", {"main_text_words": 4500, "abstract_words": 150, "display_items": 8, "references": 50}),
    ("nature-immunology", "Nature Immunology", "nature", "Basic and translational immunologists studying immune development, regulation, infection, and disease.", ["Article", "Brief Communication", "Resource", "Review"], ["immunology", "immune", "infection", "inflammation", "host defense"], "https://www.nature.com/ni/content", {"abstract_words": 150, "display_items": 8, "references": 50}),
    ("nature-cancer", "Nature Cancer", "nature", "Cancer researchers and clinicians focused on mechanism, prevention, diagnosis, and therapy.", ["Article", "Brief Communication", "Analysis", "Resource"], ["cancer", "oncology", "tumor", "therapy", "metastasis"], "https://www.nature.com/natcancer/content", {}),
    ("nature-cell-biology", "Nature Cell Biology", "nature", "Cell biologists seeking mechanistic insight with broad relevance across cellular systems.", ["Article", "Brief Communication", "Resource", "Review"], ["cell biology", "mechanism", "organelle", "signaling", "development"], "https://www.nature.com/ncb/content", {"main_text_words": 5000, "abstract_words": 150, "display_items": 8, "references": 50}),
    ("nature-microbiology", "Nature Microbiology", "nature", "Microbiologists studying bacteria, archaea, fungi, parasites, viruses, and microbial communities.", ["Article", "Brief Communication", "Resource", "Analysis"], ["microbiology", "pathogen", "microbiome", "infection", "microbial ecology"], "https://www.nature.com/nmicrobiol/content", {}),
    ("nature-metabolism", "Nature Metabolism", "nature", "Researchers studying metabolism across molecules, cells, organisms, and human disease.", ["Article", "Brief Communication", "Resource", "Analysis"], ["metabolism", "metabolic disease", "physiology", "nutrition", "systems biology"], "https://www.nature.com/natmetab/content", {}),
    ("nature-biomedical-engineering", "Nature Biomedical Engineering", "nature", "Engineers, physical scientists, biologists, and clinicians developing technologies for health.", ["Article", "Review", "Perspective", "Analysis"], ["biomedical engineering", "device", "diagnostics", "biomaterials", "technology"], "https://www.nature.com/natbiomedeng/submission-guidelines/aip-and-formatting", {}),
    ("nature-communications", "Nature Communications", "nature", "Specialists across the natural and health sciences seeking substantial, well-supported advances.", ["Article", "Review", "Perspective"], ["biology", "medicine", "methods", "genomics", "multidisciplinary"], "https://www.nature.com/ncomms/submit/article", {"main_text_words": 5000, "abstract_words": 200, "display_items": 10, "references": 70}),
    ("communications-biology", "Communications Biology", "nature", "Biologists across scales interested in rigorous advances of specialist and cross-field interest.", ["Article", "Registered Report", "Review"], ["biology", "cell biology", "genomics", "ecology", "physiology"], "https://www.nature.com/commsbio/submission-guidelines", {}),
    ("nature-structural-molecular-biology", "Nature Structural & Molecular Biology", "nature", "Structural and molecular biologists studying mechanism from molecules to cellular assemblies.", ["Article", "Brief Communication", "Resource", "Review"], ["structural biology", "molecular biology", "biochemistry", "cryo-EM", "mechanism"], "https://www.nature.com/nsmb/content", {"main_text_words": 4500, "abstract_words": 150, "display_items": 8}),
    ("scientific-data", "Scientific Data", "nature", "Researchers and data stewards seeking reusable, well-described scientific datasets.", ["Data Descriptor", "Analysis", "Comment"], ["data resource", "dataset", "reuse", "standards", "repository"], "https://www.nature.com/sdata/publish/submission-guidelines", {}),
    ("science", "Science", "science", "A broad international scientific readership seeking major conceptual or societal advances.", ["Research Article", "Report", "Review", "Perspective"], ["multidisciplinary", "conceptual advance", "biology", "medicine", "technology"], "https://www.science.org/content/page/science-information-authors", {}),
    ("science-translational-medicine", "Science Translational Medicine", "science", "Translational researchers and clinicians moving discoveries toward human health applications.", ["Research Article", "Research Resource", "Review", "Perspective"], ["translational", "clinical", "therapeutics", "diagnostics", "disease"], "https://www.science.org/journal/stm/information-for-authors", {}),
    ("science-immunology", "Science Immunology", "science", "Immunologists across basic, translational, and clinical research.", ["Research Article", "Research Resource", "Review"], ["immunology", "immune", "infection", "inflammation", "therapy"], "https://www.science.org/journal/sciimmunol/information-for-authors", {}),
    ("science-signaling", "Science Signaling", "science", "Researchers studying cellular communication, signal transduction, and therapeutic intervention.", ["Research Article", "Research Resource", "Review"], ["signaling", "cell communication", "kinase", "pathway", "mechanism"], "https://www.science.org/journal/signaling/information-for-authors", {}),
    ("science-advances", "Science Advances", "science", "A broad scientific audience interested in rigorous advances across disciplines.", ["Research Article", "Review"], ["multidisciplinary", "biology", "medicine", "technology", "methods"], "https://www.science.org/journal/sciadv/information-for-authors", {}),
    ("cell", "Cell", "cell_press", "A broad life-science readership seeking deep mechanism and exceptional conceptual advance.", ["Article", "Resource", "Review", "Perspective"], ["cell biology", "mechanism", "multidisciplinary", "disease", "technology"], "https://www.cell.com/cell/home", {}),
    ("cell-stem-cell", "Cell Stem Cell", "cell_press", "Stem-cell, developmental, regenerative-medicine, and disease-modeling researchers.", ["Article", "Resource", "Clinical and Translational Report", "Review"], ["stem cell", "development", "regeneration", "organoid", "cell therapy"], "https://www.cell.com/cell-stem-cell/home", {}),
    ("cancer-cell", "Cancer Cell", "cell_press", "Cancer biologists and oncologists seeking mechanistic and translational advances.", ["Article", "Resource", "Clinical and Translational Report", "Review"], ["cancer", "oncology", "tumor", "therapy", "immuno-oncology"], "https://www.cell.com/cancer-cell/home", {}),
    ("immunity", "Immunity", "cell_press", "Immunologists studying immune mechanisms in health and disease.", ["Article", "Resource", "Review", "Perspective"], ["immunology", "immune", "infection", "inflammation", "host defense"], "https://www.cell.com/immunity/home", {}),
    ("neuron", "Neuron", "cell_press", "Neuroscientists studying molecular, cellular, systems, cognitive, and disease mechanisms.", ["Article", "Resource", "NeuroView", "Review"], ["neuroscience", "brain", "circuit", "behavior", "neurological disease"], "https://www.cell.com/neuron/home", {}),
    ("molecular-cell", "Molecular Cell", "cell_press", "Molecular and cell biologists interested in mechanistic insight into gene regulation and cellular function.", ["Article", "Resource", "Short Article", "Review"], ["molecular biology", "gene regulation", "chromatin", "RNA", "mechanism"], "https://www.cell.com/molecular-cell/home", {}),
    ("cell-metabolism", "Cell Metabolism", "cell_press", "Researchers studying metabolic control from molecules to physiology and disease.", ["Article", "Resource", "Clinical and Translational Report", "Review"], ["metabolism", "physiology", "nutrition", "metabolic disease", "systems biology"], "https://www.cell.com/cell-metabolism/home", {}),
    ("cell-host-microbe", "Cell Host & Microbe", "cell_press", "Researchers studying microbes, hosts, microbiota, infection, and immunity.", ["Article", "Resource", "Short Article", "Review"], ["microbiology", "infection", "microbiome", "host pathogen", "immunity"], "https://www.cell.com/cell-host-microbe/home", {}),
    ("developmental-cell", "Developmental Cell", "cell_press", "Cell and developmental biologists studying morphogenesis, fate, tissue organization, and mechanism.", ["Article", "Resource", "Short Article", "Review"], ["development", "cell biology", "morphogenesis", "cell fate", "tissue"], "https://www.cell.com/developmental-cell/home", {}),
    ("cell-reports-medicine", "Cell Reports Medicine", "cell_press", "Biomedical and clinical researchers seeking mechanistic and translational studies with human relevance.", ["Article", "Resource", "Report", "Review"], ["medicine", "translational", "clinical", "disease", "biomarker"], "https://www.cell.com/cell-reports-medicine/home", {}),
    ("current-biology", "Current Biology", "cell_press", "A broad biology readership interested in important, accessible advances across organisms and scales.", ["Article", "Report", "Resource", "Review"], ["biology", "evolution", "neuroscience", "cell biology", "ecology"], "https://www.cell.com/current-biology/home", {}),
    ("the-lancet", "The Lancet", "lancet", "Clinicians, researchers, policy makers, and global health leaders.", ["Article", "Randomised Controlled Trial", "Review", "Series"], ["clinical", "global health", "public health", "policy", "trial"], "https://www.thelancet.com/journals/lancet/home", {}),
    ("lancet-oncology", "The Lancet Oncology", "lancet", "Oncologists and cancer researchers focused on practice-changing clinical evidence.", ["Article", "Clinical Picture", "Review", "Personal View"], ["oncology", "cancer", "trial", "therapy", "diagnostics"], "https://www.thelancet.com/journals/lanonc/home", {}),
    ("lancet-neurology", "The Lancet Neurology", "lancet", "Neurologists and neuroscience clinicians seeking clinically relevant evidence.", ["Article", "Review", "Personal View", "Clinical Picture"], ["neurology", "brain", "clinical", "trial", "neurological disease"], "https://www.thelancet.com/journals/laneur/home", {}),
    ("lancet-infectious-diseases", "The Lancet Infectious Diseases", "lancet", "Infectious-disease clinicians, microbiologists, epidemiologists, and policy makers.", ["Article", "Review", "Personal View", "Clinical Picture"], ["infectious disease", "pathogen", "epidemiology", "public health", "trial"], "https://www.thelancet.com/journals/laninf/home", {}),
    ("lancet-digital-health", "The Lancet Digital Health", "lancet", "Clinicians, data scientists, engineers, and policy makers evaluating digital health technologies.", ["Article", "Review", "Personal View", "Comment"], ["digital health", "machine learning", "clinical AI", "diagnostics", "implementation"], "https://www.thelancet.com/journals/landig/home", {}),
    ("lancet-haematology", "The Lancet Haematology", "lancet", "Haematologists and researchers studying blood disorders and therapies.", ["Article", "Review", "Personal View", "Clinical Picture"], ["hematology", "blood", "leukemia", "trial", "therapy"], "https://www.thelancet.com/journals/lanhae/home", {}),
    ("lancet-respiratory-medicine", "The Lancet Respiratory Medicine", "lancet", "Respiratory clinicians and researchers focused on lung disease and care.", ["Article", "Review", "Personal View", "Clinical Picture"], ["respiratory", "lung", "clinical", "trial", "infection"], "https://www.thelancet.com/journals/lanres/home", {}),
    ("lancet-gastroenterology-hepatology", "The Lancet Gastroenterology & Hepatology", "lancet", "Gastroenterology and hepatology clinicians and researchers.", ["Article", "Review", "Personal View", "Clinical Picture"], ["gastroenterology", "hepatology", "liver", "gut", "trial"], "https://www.thelancet.com/journals/langas/home", {}),
    ("nejm", "New England Journal of Medicine", "nejm", "Clinicians and biomedical researchers seeking practice-changing medical evidence.", ["Original Article", "Brief Report", "Review Article", "Special Article"], ["clinical", "medicine", "trial", "diagnostics", "public health"], "https://www.nejm.org/author-center/article-types", {}),
    ("jama", "JAMA", "jama", "Clinicians, health researchers, and policy makers seeking rigorous evidence with broad medical relevance.", ["Original Investigation", "Research Letter", "Review", "Clinical Trial"], ["clinical", "medicine", "health policy", "trial", "diagnostics"], "https://jamanetwork.com/journals/jama/pages/instructions-for-authors", {}),
    ("bmj", "The BMJ", "bmj", "Clinicians, researchers, patients, and policy makers interested in evidence that informs care and health systems.", ["Research", "Systematic Review", "Analysis", "Education"], ["clinical", "public health", "health policy", "trial", "evidence synthesis"], "https://www.bmj.com/about-bmj/resources-authors/article-types", {}),
    ("pnas", "Proceedings of the National Academy of Sciences", "general_biology", "A broad scientific readership spanning biological, physical, and social sciences.", ["Research Report", "Brief Report", "Review", "Perspective"], ["multidisciplinary", "biology", "medicine", "methods", "evolution"], "https://www.pnas.org/author-center/submitting-your-manuscript", {}),
    ("elife", "eLife", "general_biology", "Life scientists seeking transparent assessment of important research across biology and medicine.", ["Research Article", "Short Report", "Tools and Resources", "Review Article"], ["biology", "medicine", "methods", "development", "neuroscience"], "https://elifesciences.org/articles/research-article", {}),
    ("embo-journal", "The EMBO Journal", "general_biology", "Molecular and cell biologists seeking mechanistic and conceptual advances.", ["Research Article", "Report", "Review", "Resource"], ["molecular biology", "cell biology", "mechanism", "gene regulation", "development"], "https://www.embopress.org/page/journal/14602075/authorguide", {}),
    ("molecular-systems-biology", "Molecular Systems Biology", "general_biology", "Systems and synthetic biologists integrating quantitative experiments, computation, and theory.", ["Research Article", "Report", "Method", "Resource"], ["systems biology", "computational biology", "network", "multiomics", "modeling"], "https://www.embopress.org/page/journal/17444292/authorguide", {}),
    ("genome-biology", "Genome Biology", "general_biology", "Genomics and post-genomics researchers across basic, biomedical, and computational biology.", ["Research", "Methodology", "Software", "Review"], ["genomics", "single-cell", "bioinformatics", "methods", "functional genomics"], "https://genomebiology.biomedcentral.com/submission-guidelines", {}),
    ("genome-research", "Genome Research", "general_biology", "Genome scientists studying structure, function, evolution, technology, and computation.", ["Research", "Methods", "Resource", "Review"], ["genomics", "genome", "methods", "bioinformatics", "functional genomics"], "https://genome.cshlp.org/site/misc/ifora.xhtml", {}),
    ("nucleic-acids-research", "Nucleic Acids Research", "general_biology", "Researchers studying nucleic-acid biology, genomics, computational resources, and databases.", ["Research Article", "Methods Article", "Database Issue", "Web Server Issue"], ["DNA", "RNA", "genomics", "database", "bioinformatics"], "https://academic.oup.com/nar/pages/author-guidelines", {"abstract_words": 200}),
    ("bioinformatics", "Bioinformatics", "general_biology", "Computational biologists and bioinformaticians developing methods, software, and analyses.", ["Original Paper", "Application Note", "Review", "Discovery Note"], ["bioinformatics", "software", "algorithm", "computational biology", "benchmark"], "https://academic.oup.com/bioinformatics/pages/author-guidelines", {"main_text_words": 5000}),
    ("plos-biology", "PLOS Biology", "general_biology", "A broad biology readership seeking important, rigorous, openly accessible research.", ["Research Article", "Methods and Resources", "Short Report", "Review"], ["biology", "open science", "methods", "development", "genomics"], "https://journals.plos.org/plosbiology/s/submission-guidelines", {}),
    ("blood", "Blood", "general_biology", "Hematologists and researchers studying blood biology, malignancy, and clinical hematology.", ["Regular Article", "Brief Report", "Review", "Clinical Trial"], ["hematology", "blood", "leukemia", "immunology", "clinical"], "https://ashpublications.org/blood/pages/manuscript_types", {}),
    ("circulation", "Circulation", "general_biology", "Cardiovascular clinicians and scientists seeking mechanistic and clinical advances.", ["Original Research Article", "Research Letter", "Review", "Clinical Trial"], ["cardiovascular", "heart", "clinical", "trial", "vascular"], "https://www.ahajournals.org/circ/author-instructions", {}),
    ("ca-cancer-j-clin", "CA: A Cancer Journal for Clinicians", "general_biology", "Clinicians, cancer researchers, and policy leaders seeking authoritative syntheses that can change oncology practice.", ["Review", "Guideline", "Special Article"], ["oncology", "cancer prevention", "clinical practice", "epidemiology", "guideline"], "https://acsjournals.onlinelibrary.wiley.com/journal/15424863", {}),
    ("nature-reviews-molecular-cell-biology", "Nature Reviews Molecular Cell Biology", "nature", "Researchers seeking authoritative syntheses across molecular and cell biology.", ["Review", "Perspective", "Comment"], ["molecular biology", "cell biology", "mechanism", "gene regulation", "organelle"], "https://www.nature.com/nrm/content", {}),
    ("nature-reviews-microbiology", "Nature Reviews Microbiology", "nature", "Microbiologists and infection researchers seeking broad, authoritative syntheses.", ["Review", "Perspective", "Comment"], ["microbiology", "infection", "microbiome", "pathogen", "host defense"], "https://www.nature.com/nrmicro/content", {}),
    ("nature-reviews-clinical-oncology", "Nature Reviews Clinical Oncology", "nature", "Oncologists and cancer researchers seeking clinically consequential synthesis.", ["Review", "Perspective", "Consensus Statement"], ["oncology", "clinical cancer", "therapy", "diagnostics", "trial"], "https://www.nature.com/nrclinonc/content", {}),
    ("nature-reviews-drug-discovery", "Nature Reviews Drug Discovery", "nature", "Drug-discovery scientists, translational researchers, and industry leaders.", ["Review", "Perspective", "Analysis"], ["drug discovery", "pharmacology", "therapeutics", "biotechnology", "translation"], "https://www.nature.com/nrd/content", {}),
    ("signal-transduction-targeted-therapy", "Signal Transduction and Targeted Therapy", "nature", "Researchers connecting signaling mechanisms with targeted therapeutic development.", ["Article", "Review", "Perspective"], ["signaling", "targeted therapy", "molecular medicine", "cancer", "immunology"], "https://www.nature.com/sigtrans/", {}),
    ("annals-of-oncology", "Annals of Oncology", "general_biology", "Medical oncologists and translational cancer researchers focused on practice-changing evidence.", ["Original Article", "Review", "Guideline", "Letter"], ["oncology", "clinical trial", "precision medicine", "cancer therapy", "biomarker"], "https://www.annalsofoncology.org/content/authorinfo", {}),
    ("nature-reviews-disease-primers", "Nature Reviews Disease Primers", "nature", "Multidisciplinary readers seeking integrated disease mechanisms, diagnosis, management, and outlook.", ["Primer", "Perspective", "Comment"], ["disease mechanism", "diagnosis", "clinical management", "epidemiology", "translation"], "https://www.nature.com/nrdp/content", {}),
    ("world-psychiatry", "World Psychiatry", "general_biology", "Psychiatrists, neuroscientists, and mental-health policy readers seeking field-wide evidence.", ["Research Report", "Review", "Forum", "Perspective"], ["psychiatry", "mental health", "clinical neuroscience", "public health", "policy"], "https://onlinelibrary.wiley.com/page/journal/20515545/homepage/forauthors.html", {}),
    ("nature-reviews-cancer", "Nature Reviews Cancer", "nature", "Cancer researchers and clinicians seeking authoritative mechanistic and translational synthesis.", ["Review", "Perspective", "Comment"], ["cancer biology", "oncology", "therapy", "tumor microenvironment", "metastasis"], "https://www.nature.com/nrc/content", {}),
    ("nature-reviews-genetics", "Nature Reviews Genetics", "nature", "Geneticists and genomic scientists seeking authoritative synthesis across inheritance and genome function.", ["Review", "Perspective", "Comment"], ["genetics", "genomics", "inheritance", "functional genomics", "population genetics"], "https://www.nature.com/nrg/content", {}),
    ("nature-reviews-cardiology", "Nature Reviews Cardiology", "nature", "Cardiovascular clinicians and scientists seeking integrated clinical and mechanistic reviews.", ["Review", "Perspective", "Consensus Statement"], ["cardiology", "cardiovascular", "heart", "vascular", "clinical"], "https://www.nature.com/nrcardio/content", {}),
    ("nature-reviews-immunology", "Nature Reviews Immunology", "nature", "Immunologists seeking authoritative conceptual and translational synthesis.", ["Review", "Perspective", "Comment"], ["immunology", "immune regulation", "infection", "inflammation", "therapy"], "https://www.nature.com/nri/content", {}),
    ("european-heart-journal", "European Heart Journal", "general_biology", "Cardiovascular clinicians and scientists focused on high-impact clinical and translational research.", ["Original Article", "Clinical Research", "Review", "Guideline"], ["cardiology", "cardiovascular", "trial", "heart disease", "vascular"], "https://academic.oup.com/eurheartj/pages/General_Instructions", {}),
    ("journal-of-clinical-oncology", "Journal of Clinical Oncology", "general_biology", "Clinical oncologists and cancer researchers seeking definitive patient-centered evidence.", ["Original Report", "Clinical Trial", "Review", "Special Article"], ["clinical oncology", "cancer therapy", "trial", "biomarker", "outcomes"], "https://ascopubs.org/jco/authors/manuscript-guidelines", {}),
    ("nature-reviews-bioengineering", "Nature Reviews Bioengineering", "nature", "Bioengineers, biomedical scientists, and clinicians seeking field-defining synthesis.", ["Review", "Perspective", "Comment"], ["bioengineering", "biomaterials", "device", "synthetic biology", "translation"], "https://www.nature.com/natrevbioeng/content", {}),
    ("molecular-cancer", "Molecular Cancer", "general_biology", "Cancer biologists and translational researchers connecting mechanism to therapeutic opportunity.", ["Research", "Review", "Methodology"], ["molecular oncology", "cancer biology", "therapy", "biomarker", "tumor"], "https://molecular-cancer.biomedcentral.com/submission-guidelines", {}),
    ("journal-of-hepatology", "Journal of Hepatology", "general_biology", "Hepatologists and liver researchers focused on mechanistic and clinical advances.", ["Original Article", "Rapid Communication", "Review", "Guideline"], ["hepatology", "liver", "clinical trial", "metabolism", "infection"], "https://www.journal-of-hepatology.eu/content/authorinfo", {}),
    ("nature-reviews-endocrinology", "Nature Reviews Endocrinology", "nature", "Endocrinologists and metabolism researchers seeking authoritative clinical and mechanistic synthesis.", ["Review", "Perspective", "Consensus Statement"], ["endocrinology", "metabolism", "diabetes", "hormone", "clinical"], "https://www.nature.com/nrendo/content", {}),
    ("nature-nanotechnology", "Nature Nanotechnology", "nature", "Researchers developing nanoscale concepts and technologies across biology, medicine, physics, and materials.", ["Article", "Letter", "Review", "Analysis"], ["nanotechnology", "nanomedicine", "materials", "device", "delivery"], "https://www.nature.com/nnano/content", {}),
    ("lancet-diabetes-endocrinology", "The Lancet Diabetes & Endocrinology", "lancet", "Clinicians and researchers focused on diabetes, endocrinology, metabolism, and population health.", ["Article", "Review", "Series", "Personal View"], ["diabetes", "endocrinology", "metabolism", "trial", "public health"], "https://www.thelancet.com/journals/landia/home", {}),
    ("physiological-reviews", "Physiological Reviews", "general_biology", "Physiologists and biomedical scientists seeking authoritative integrative reviews.", ["Comprehensive Review", "Short Review", "Perspective"], ["physiology", "homeostasis", "organ system", "mechanism", "disease"], "https://journals.physiology.org/author-info.physrev", {}),
    ("nature-reviews-rheumatology", "Nature Reviews Rheumatology", "nature", "Rheumatologists and immunologists seeking clinical and mechanistic synthesis.", ["Review", "Perspective", "Consensus Statement"], ["rheumatology", "autoimmunity", "inflammation", "clinical", "therapy"], "https://www.nature.com/nrrheum/content", {}),
    ("molecular-plant", "Molecular Plant", "cell_press", "Plant biologists seeking mechanistic, genomic, and translational advances.", ["Article", "Resource", "Review", "Perspective"], ["plant biology", "molecular biology", "genomics", "development", "crop"], "https://www.cell.com/molecular-plant/home", {}),
    ("nature-reviews-neurology", "Nature Reviews Neurology", "nature", "Neurologists and neuroscientists seeking authoritative clinical synthesis.", ["Review", "Perspective", "Consensus Statement"], ["neurology", "brain disease", "clinical neuroscience", "diagnostics", "therapy"], "https://www.nature.com/nrneurol/content", {}),
    ("cell-research", "Cell Research", "nature", "Cell and molecular biologists seeking broadly important mechanistic advances.", ["Article", "Letter", "Review"], ["cell biology", "molecular biology", "mechanism", "genomics", "disease"], "https://www.nature.com/cr/authors-and-referees", {}),
    ("gastroenterology", "Gastroenterology", "general_biology", "Gastroenterologists and digestive-disease researchers seeking mechanistic and clinical advances.", ["Original Research", "Clinical Trial", "Review", "Guideline"], ["gastroenterology", "gut", "liver", "microbiome", "clinical"], "https://www.gastrojournal.org/content/authorinfo", {}),
    ("cancer-discovery", "Cancer Discovery", "general_biology", "Cancer researchers and clinicians seeking major mechanistic and translational discoveries.", ["Research Article", "Research Brief", "Review", "Perspective"], ["cancer biology", "oncology", "precision medicine", "therapy", "tumor"], "https://aacrjournals.org/cancerdiscovery/pages/instructions-for-authors", {}),
    ("european-urology", "European Urology", "general_biology", "Urologists and researchers focused on clinically consequential urologic evidence.", ["Original Article", "Review", "Guideline", "Research Letter"], ["urology", "oncology", "surgery", "clinical trial", "outcomes"], "https://www.europeanurology.com/content/authorinfo", {}),
    ("nature-reviews-neuroscience", "Nature Reviews Neuroscience", "nature", "Neuroscientists seeking authoritative synthesis from molecules to cognition and disease.", ["Review", "Perspective", "Comment"], ["neuroscience", "brain", "circuit", "cognition", "neurological disease"], "https://www.nature.com/nrn/content", {}),
    ("cancer-communications", "Cancer Communications", "general_biology", "Cancer researchers and clinicians focused on translational and clinical oncology.", ["Research Article", "Review", "Method"], ["cancer", "oncology", "therapy", "biomarker", "translation"], "https://onlinelibrary.wiley.com/page/journal/25233548/homepage/forauthors.html", {}),
    ("lancet-public-health", "The Lancet Public Health", "lancet", "Public-health researchers, clinicians, and policy makers seeking population-level evidence.", ["Article", "Review", "Comment", "Health Policy"], ["public health", "epidemiology", "policy", "population", "health equity"], "https://www.thelancet.com/journals/lanpub/home", {}),
    ("nature-aging", "Nature Aging", "nature", "Researchers studying aging mechanisms, longevity, age-related disease, and healthy lifespan.", ["Article", "Resource", "Review", "Perspective"], ["aging", "longevity", "geroscience", "neuroscience", "age-related disease"], "https://www.nature.com/nataging/content", {}),
    ("jama-internal-medicine", "JAMA Internal Medicine", "jama", "Internists, health researchers, and policy makers seeking rigorous evidence that changes care.", ["Original Investigation", "Research Letter", "Review", "Clinical Trial"], ["internal medicine", "clinical", "health policy", "trial", "outcomes"], "https://jamanetwork.com/journals/jamainternalmedicine/pages/instructions-for-authors", {}),
    ("trends-cell-biology", "Trends in Cell Biology", "cell_press", "Cell biologists seeking concise, authoritative synthesis of emerging concepts.", ["Review", "Opinion", "Forum"], ["cell biology", "organelle", "signaling", "development", "mechanism"], "https://www.cell.com/trends/cell-biology/home", {}),
    ("jama-oncology", "JAMA Oncology", "jama", "Oncologists and cancer researchers seeking clinically influential evidence.", ["Original Investigation", "Research Letter", "Review", "Clinical Trial"], ["oncology", "cancer", "trial", "therapy", "outcomes"], "https://jamanetwork.com/journals/jamaoncology/pages/instructions-for-authors", {}),
    ("cellular-molecular-immunology", "Cellular & Molecular Immunology", "nature", "Immunologists seeking mechanistic and translational advances.", ["Article", "Review", "Perspective"], ["immunology", "immune regulation", "inflammation", "infection", "therapy"], "https://www.nature.com/cmi/authors-and-referees", {}),
    ("jama-neurology", "JAMA Neurology", "jama", "Neurologists and clinical neuroscientists seeking practice-relevant evidence.", ["Original Investigation", "Research Letter", "Review", "Clinical Trial"], ["neurology", "clinical neuroscience", "brain disease", "trial", "diagnostics"], "https://jamanetwork.com/journals/jamaneurology/pages/instructions-for-authors", {}),
    ("cancer-research", "Cancer Research", "general_biology", "Cancer biologists and translational researchers seeking rigorous mechanistic advances.", ["Research Article", "Priority Report", "Review"], ["cancer biology", "tumor", "metastasis", "therapy", "genomics"], "https://aacrjournals.org/cancerres/pages/instructions-for-authors", {}),
    ("lancet-global-health", "The Lancet Global Health", "lancet", "Global-health researchers, clinicians, and policy makers focused on equitable population impact.", ["Article", "Review", "Comment", "Health Policy"], ["global health", "public health", "epidemiology", "health equity", "policy"], "https://www.thelancet.com/journals/langlo/home", {}),
    ("jacc", "Journal of the American College of Cardiology", "general_biology", "Cardiovascular clinicians and researchers seeking practice-changing clinical evidence.", ["Original Research", "Clinical Trial", "Review", "State-of-the-Art Review"], ["cardiology", "heart", "clinical trial", "imaging", "outcomes"], "https://www.jacc.org/author-center", {}),
    ("lancet-microbe", "The Lancet Microbe", "lancet", "Microbiologists, infectious-disease researchers, and clinicians seeking translational evidence.", ["Article", "Review", "Comment", "Personal View"], ["microbiology", "infectious disease", "pathogen", "microbiome", "public health"], "https://www.thelancet.com/journals/lanmic/home", {}),
    ("trends-cancer", "Trends in Cancer", "cell_press", "Cancer researchers seeking concise synthesis of emerging mechanisms and therapeutic directions.", ["Review", "Opinion", "Forum"], ["cancer", "oncology", "therapy", "tumor microenvironment", "genomics"], "https://www.cell.com/trends/cancer/home", {}),
    ("lancet-psychiatry", "The Lancet Psychiatry", "lancet", "Mental-health clinicians, researchers, and policy makers seeking high-impact clinical evidence.", ["Article", "Review", "Comment", "Personal View"], ["psychiatry", "mental health", "trial", "public health", "policy"], "https://www.thelancet.com/journals/lanpsy/home", {}),
    ("lancet-planetary-health", "The Lancet Planetary Health", "lancet", "Researchers and policy makers studying environmental change and population health.", ["Article", "Review", "Comment", "Health Policy"], ["planetary health", "environment", "public health", "climate", "policy"], "https://www.thelancet.com/journals/lanplh/home", {}),
    ("npj-digital-medicine", "npj Digital Medicine", "nature", "Clinicians, data scientists, and engineers evaluating digital and computational health interventions.", ["Article", "Review", "Perspective", "Brief Communication"], ["digital health", "clinical AI", "medical informatics", "wearables", "implementation"], "https://www.nature.com/npjdigitalmed/submission-guidelines", {}),
]


PUBLISHER_LABELS = {
    "AMER ASSOC ADVANCEMENT SCIENCE": "AAAS",
    "AMER ASSOC CANCER RESEARCH": "American Association for Cancer Research",
    "AMER MEDICAL ASSOC": "American Medical Association",
    "AMER PHYSIOLOGICAL SOC": "American Physiological Society",
    "BMC": "Springer Nature · BMC",
    "BMJ PUBLISHING GROUP": "BMJ Group",
    "CELL PRESS": "Elsevier · Cell Press",
    "CHIN SOCIETY IMMUNOLOGY": "Chinese Society for Immunology · Springer Nature",
    "COLD SPRING HARBOR LAB PRESS": "Cold Spring Harbor Laboratory Press",
    "ELIFE SCIENCES PUBL LTD": "eLife Sciences Publications",
    "ELSEVIER": "Elsevier",
    "ELSEVIER INC": "Elsevier",
    "ELSEVIER SCI LTD": "Elsevier",
    "ELSEVIER SCIENCE INC": "Elsevier",
    "LIPPINCOTT WILLIAMS & WILKINS": "Wolters Kluwer",
    "MASSACHUSETTS MEDICAL SOC": "Massachusetts Medical Society",
    "NATL ACAD SCIENCES": "National Academy of Sciences",
    "NATURE PORTFOLIO": "Springer Nature · Nature Portfolio",
    "OXFORD UNIV PRESS": "Oxford University Press",
    "PUBLIC LIBRARY SCIENCE": "Public Library of Science",
    "SPRINGER NATURE": "Springer Nature",
    "SPRINGERNATURE": "Springer Nature",
    "W B SAUNDERS CO-ELSEVIER INC": "Elsevier",
    "WILEY": "Wiley",
}

PUBLISHER_BY_ID = {
    "annals-of-oncology": "European Society for Medical Oncology · Elsevier",
    "blood": "American Society of Hematology",
    "ca-cancer-j-clin": "American Cancer Society · Wiley",
    "cancer-discovery": "American Association for Cancer Research",
    "cancer-research": "American Association for Cancer Research",
    "circulation": "American Heart Association · Wolters Kluwer",
    "european-heart-journal": "European Society of Cardiology · Oxford University Press",
    "european-urology": "European Association of Urology · Elsevier",
    "gastroenterology": "American Gastroenterological Association · Elsevier",
    "jacc": "American College of Cardiology · Elsevier",
    "journal-of-clinical-oncology": "American Society of Clinical Oncology",
    "journal-of-hepatology": "European Association for the Study of the Liver · Elsevier",
    "world-psychiatry": "World Psychiatric Association · Wiley",
}

PUBLISHER_BY_FAMILY = {
    "bmj": "BMJ Group",
    "cell_press": "Elsevier · Cell Press",
    "jama": "American Medical Association",
    "lancet": "Elsevier · The Lancet Group",
    "nejm": "Massachusetts Medical Society",
    "science": "AAAS",
}


def _load_metrics() -> dict[str, dict]:
    if not METRICS_PATH.is_file():
        raise RuntimeError(f"reviewed metric source is unavailable: {METRICS_PATH}")
    with METRICS_PATH.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle, delimiter="\t"))
    required = {
        "journal_id",
        "publisher",
        "issn",
        "eissn",
        "jif",
        "category",
        "edition",
        "quartile",
        "source_level",
        "source_name",
        "source_url",
        "retrieved_on",
        "source_artifact_sha256",
    }
    if not source_rows or set(source_rows[0]) != required:
        raise RuntimeError("reviewed metric source schema is inconsistent")
    grouped: dict[str, dict] = {}
    for source_row in source_rows:
        journal_id = source_row["journal_id"].strip()
        if not journal_id:
            raise RuntimeError("metric row has no journal_id")
        raw_jif = source_row["jif"].strip()
        metric = grouped.setdefault(
            journal_id,
            {
                "edition": "2026",
                "metric_year": 2025,
                "jif": None if raw_jif == "N/A" else float(raw_jif),
                "jif_status": "not_assigned" if raw_jif == "N/A" else "reported",
                "publisher": source_row["publisher"].strip(),
                "issn": source_row["issn"].strip() or None,
                "eissn": source_row["eissn"].strip() or None,
                "categories": [],
                "source": {
                    "level": source_row["source_level"].strip(),
                    "name": source_row["source_name"].strip(),
                    "url": source_row["source_url"].strip(),
                    "retrieved_on": source_row["retrieved_on"].strip(),
                    "source_artifact_sha256": (
                        None
                        if source_row["source_artifact_sha256"].strip() == "N/A"
                        else source_row["source_artifact_sha256"].strip()
                    ),
                    "direct_clarivate_access": False,
                },
            },
        )
        expected = (
            None if raw_jif == "N/A" else float(raw_jif),
            source_row["publisher"].strip(),
            source_row["source_url"].strip(),
        )
        observed = (metric["jif"], metric["publisher"], metric["source"]["url"])
        if observed != expected:
            raise RuntimeError(f"metric rows disagree for {journal_id}")
        category = {
            "name": source_row["category"].strip(),
            "edition": source_row["edition"].strip(),
            "quartile": source_row["quartile"].strip(),
        }
        if category not in metric["categories"]:
            metric["categories"].append(category)
    for metric in grouped.values():
        metric["categories"].sort(key=lambda row: (row["name"], row["edition"], row["quartile"]))
        if not metric["categories"]:
            raise RuntimeError("journal metric has no category")
        if not metric["source"]["url"].startswith("https://"):
            raise RuntimeError("journal metric source must use HTTPS")
        if metric["source"]["level"] not in {
            "primary_clarivate",
            "secondary_institutional_jcr_repost",
            "secondary_specialist_jcr_index",
        }:
            raise RuntimeError("journal metric source level is not allowed")
        selected_record = {
            "edition": metric["edition"],
            "metric_year": metric["metric_year"],
            "jif": metric["jif"],
            "jif_status": metric["jif_status"],
            "publisher": metric["publisher"],
            "issn": metric["issn"],
            "eissn": metric["eissn"],
            "categories": metric["categories"],
            "source_level": metric["source"]["level"],
            "source_url": metric["source"]["url"],
        }
        metric["source"]["selected_record_sha256"] = hashlib.sha256(
            json.dumps(selected_record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
    return grouped


def _profile(row: tuple, metrics: dict[str, dict]) -> dict:
    journal_id, title, family_name, audience, article_types, topics, scope_url, overrides = row
    family = FAMILY_RULES[family_name]
    if journal_id not in metrics:
        raise RuntimeError(f"journal has no reviewed 2026 metric record: {journal_id}")
    journal_metric = metrics[journal_id]
    constraints = dict(family["default_constraints"])
    constraints.update(overrides)
    exact_fields = sorted({*family.get("exact_default_fields", []), *overrides})
    return {
        "id": journal_id,
        "title": title,
        "publisher": PUBLISHER_BY_ID.get(
            journal_id,
            PUBLISHER_BY_FAMILY.get(
                family_name,
                PUBLISHER_LABELS.get(journal_metric["publisher"], journal_metric["publisher"].title()),
            ),
        ),
        "publisher_family": family_name,
        "standard_version": VERSION,
        "reviewed_on": REVIEWED_ON,
        "audience": audience,
        "favored_article_types": article_types,
        "topic_fit_terms": topics,
        "preferred_study_signals": [
            "question and contribution match the declared audience",
            "claims are proportionate to design and independent validation",
            "methods, data, code, statistics, and limitations are reproducible",
        ],
        "language_style": family["language_style"],
        "required_sections": family["required_sections"],
        "constraints": constraints,
        "constraint_provenance": {
            "exact_journal_fields": exact_fields,
            "status": family["constraint_status"],
            "unknown_policy": "A null value is a mandatory live-check item before submission, not permission to ignore the field.",
        },
        "figure_and_table_requirements": family["figure_rules"],
        "reporting_requirements": family["reporting_requirements"],
        "official_sources": [scope_url, *family["official_sources"]],
        "journal_metrics": journal_metric,
        "recommendation_policy": {
            "eligible": True,
            "impact_factor_used": False,
            "acceptance_probability_claimed": False,
            "requires_project_specific_fit_review": True,
        },
    }


ZH_CATEGORIES = {
    "BIOCHEMICAL RESEARCH METHODS": "生化研究方法",
    "BIOCHEMISTRY & MOLECULAR BIOLOGY": "生物化学与分子生物学",
    "BIOLOGY": "生物学",
    "BIOPHYSICS": "生物物理学",
    "BIOTECHNOLOGY & APPLIED MICROBIOLOGY": "生物技术与应用微生物学",
    "CARDIAC & CARDIOVASCULAR SYSTEMS": "心脏与心血管系统",
    "CELL & TISSUE ENGINEERING": "细胞与组织工程",
    "CELL BIOLOGY": "细胞生物学",
    "CLINICAL NEUROLOGY": "临床神经病学",
    "CRITICAL CARE MEDICINE": "重症医学",
    "DEVELOPMENTAL BIOLOGY": "发育生物学",
    "ENDOCRINOLOGY & METABOLISM": "内分泌与代谢",
    "ENGINEERING, BIOMEDICAL": "生物医学工程",
    "ENVIRONMENTAL SCIENCES": "环境科学",
    "GASTROENTEROLOGY & HEPATOLOGY": "胃肠病学与肝病学",
    "GENETICS & HEREDITY": "遗传学与遗传",
    "GERIATRICS & GERONTOLOGY": "老年医学与老年学",
    "HEALTH CARE SCIENCES & SERVICES": "卫生保健科学与服务",
    "HEALTH POLICY & SERVICES": "卫生政策与服务",
    "HEMATOLOGY": "血液学",
    "IMMUNOLOGY": "免疫学",
    "INFECTIOUS DISEASES": "感染病学",
    "MATHEMATICAL & COMPUTATIONAL BIOLOGY": "数学与计算生物学",
    "MATERIALS SCIENCE, BIOMATERIALS": "材料科学：生物材料",
    "MATERIALS SCIENCE, MULTIDISCIPLINARY": "综合材料科学",
    "MEDICAL INFORMATICS": "医学信息学",
    "MEDICINE, GENERAL & INTERNAL": "综合与内科医学",
    "MEDICINE, RESEARCH & EXPERIMENTAL": "实验与研究医学",
    "MICROBIOLOGY": "微生物学",
    "MULTIDISCIPLINARY SCIENCES": "综合科学",
    "NANOSCIENCE & NANOTECHNOLOGY": "纳米科学与纳米技术",
    "NEUROSCIENCES": "神经科学",
    "ONCOLOGY": "肿瘤学",
    "PARASITOLOGY": "寄生虫学",
    "PERIPHERAL VASCULAR DISEASE": "外周血管疾病",
    "PHARMACOLOGY & PHARMACY": "药理学与药学",
    "PHYSIOLOGY": "生理学",
    "PLANT SCIENCES": "植物科学",
    "PSYCHIATRY": "精神病学",
    "PUBLIC, ENVIRONMENTAL & OCCUPATIONAL HEALTH": "公共、环境与职业健康",
    "RESPIRATORY SYSTEM": "呼吸系统",
    "RHEUMATOLOGY": "风湿病学",
    "UROLOGY & NEPHROLOGY": "泌尿学与肾脏学",
    "VIROLOGY": "病毒学",
}


def _metric_source_label(level: str, *, zh: bool) -> str:
    labels = {
        "primary_clarivate": ("Clarivate JCR / Journals API", "Clarivate JCR / Journals API"),
        "secondary_institutional_jcr_repost": (
            "Institutional JCR repost (secondary)",
            "高校公开转载的 JCR 数据（二级来源）",
        ),
        "secondary_specialist_jcr_index": (
            "Specialist JCR index (secondary fallback)",
            "专业期刊指标索引（二级后备来源）",
        ),
    }
    return labels[level][1 if zh else 0]


def _coverage_table(profiles: list[dict], *, zh: bool) -> str:
    if zh:
        lines = [
            "| 期刊 | 出版机构 | JCR 学科类别 | JCR 2026 分区 | 2025 JIF | 指标来源 |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    else:
        lines = [
            "| Journal | Publisher / publishing organization | JCR categories | JCR 2026 quartiles | 2025 JIF | Metric provenance |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    for profile in profiles:
        metric = profile["journal_metrics"]
        categories = []
        quartiles = []
        for category in metric["categories"]:
            category_name = (
                ZH_CATEGORIES.get(category["name"], category["name"])
                if zh
                else category["name"].title()
            )
            categories.append(f"{category_name} ({category['edition']})")
            quartiles.append(f"{category_name}: {category['quartile']}")
        jif = "未获分配" if zh and metric["jif"] is None else ("Not assigned" if metric["jif"] is None else f"{metric['jif']:.1f}")
        source = metric["source"]
        source_label = _metric_source_label(source["level"], zh=zh)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"[{profile['title']}]({profile['official_sources'][0]})",
                    profile["publisher"],
                    "<br>".join(categories),
                    "<br>".join(quartiles),
                    jif,
                    f"[{source_label}]({source['url']})",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _refresh_coverage_table(path: Path, profiles: list[dict], *, zh: bool) -> None:
    start = "<!-- journal-coverage-table:start -->"
    end = "<!-- journal-coverage-table:end -->"
    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError(f"journal coverage markers are inconsistent: {path}")
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    rendered = f"{before}{start}\n{_coverage_table(profiles, zh=zh)}\n{end}{after}"
    path.write_text(rendered, encoding="utf-8")


def main() -> None:
    if len(JOURNALS) != 100:
        raise RuntimeError("active journal catalog must contain exactly 100 journals")
    metrics = _load_metrics()
    journal_ids = {row[0] for row in JOURNALS}
    if set(metrics) != journal_ids:
        missing = sorted(journal_ids - set(metrics))
        extra = sorted(set(metrics) - journal_ids)
        raise RuntimeError(f"metric coverage mismatch; missing={missing}; extra={extra}")
    profiles = [_profile(row, metrics) for row in JOURNALS]
    profiles.sort(
        key=lambda row: (
            row["journal_metrics"]["jif"] is None,
            -(row["journal_metrics"]["jif"] or 0.0),
            row["title"].casefold(),
        )
    )
    if len({row["id"] for row in profiles}) != len(profiles):
        raise RuntimeError("journal IDs must be unique")
    metrics_source_sha256 = hashlib.sha256(METRICS_PATH.read_bytes()).hexdigest()
    snapshot = {
        "schema_version": 1,
        "catalog_version": VERSION,
        "reviewed_on": REVIEWED_ON,
        "source_policy": {
            "submission_rules": (
                "Only publisher or journal author instructions, content definitions, scope pages, and reporting "
                "standards may define submission rules. Unknown numerical limits remain null."
            ),
            "journal_metrics": (
                "JIF, JCR categories, editions, and quartiles prefer direct Clarivate JCR or Journals API records. "
                "When access is unavailable, reviewed institutional reposts of the same annual JCR export may be "
                "used as explicitly labelled secondary evidence; specialist indexes are allowed only as a "
                "declared fallback. CiteScore and SJR must never be relabelled as JIF or JCR quartiles."
            ),
            "publisher_cross_check": (
                "Publisher and journal sites verify title identity, publisher, scope, and author guidance; they "
                "do not silently replace the recorded JCR provenance."
            ),
        },
        "journal_count": len(profiles),
        "metric_source_manifest": {
            "file": str(METRICS_PATH.relative_to(ROOT)),
            "sha256": metrics_source_sha256,
            "selected_journal_count": len(metrics),
        },
        "journals": profiles,
    }
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_path = OUT_ROOT / f"v{VERSION}.json"
    payload = json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    snapshot_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    _refresh_coverage_table(ROOT / "docs" / "journal-standards.md", profiles, zh=False)
    _refresh_coverage_table(ROOT / "docs" / "journal-standards.zh-CN.md", profiles, zh=True)
    index = {
        "schema_version": 1,
        "active_catalog_version": VERSION,
        "active_catalog_file": snapshot_path.name,
        "active_catalog_sha256": digest,
        "reviewed_on": REVIEWED_ON,
        "journal_count": len(profiles),
        "metric_source_file": str(METRICS_PATH.relative_to(ROOT)),
        "metric_source_sha256": metrics_source_sha256,
        "update_policy": {
            "history_is_immutable": True,
            "one_journal_may_advance_independently": True,
            "source_change_requires_new_version": True,
            "unverified_required_field_blocks_submission_ready": True,
            "metric_source_tiers_are_enforced": True,
            "active_catalog_is_sorted_by_descending_jif": True,
        },
        "journal_versions": {
            row["id"]: {
                "active_version": row["standard_version"],
                "source_file": snapshot_path.name,
                "reviewed_on": row["reviewed_on"],
            }
            for row in profiles
        },
    }
    (OUT_ROOT / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"catalog": str(snapshot_path), "journals": len(profiles), "sha256": digest}, sort_keys=True))


if __name__ == "__main__":
    main()
