#!/usr/bin/env python3
"""Build the reviewed, versioned journal-standard catalog.

The catalog deliberately distinguishes exact journal rules from publisher-wide
guidance and from fields that the publisher does not state publicly. Unknown
limits remain null and become manual submission checks; they are never filled
from convention or memory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "biomed_workbench" / "knowledge" / "journal_standards"
VERSION = "2026.07.31"
REVIEWED_ON = "2026-07-31"


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
]


def _profile(row: tuple) -> dict:
    journal_id, title, family_name, audience, article_types, topics, scope_url, overrides = row
    family = FAMILY_RULES[family_name]
    constraints = dict(family["default_constraints"])
    constraints.update(overrides)
    exact_fields = sorted({*family.get("exact_default_fields", []), *overrides})
    return {
        "id": journal_id,
        "title": title,
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
        "recommendation_policy": {
            "eligible": True,
            "impact_factor_used": False,
            "acceptance_probability_claimed": False,
            "requires_project_specific_fit_review": True,
        },
    }


def main() -> None:
    if len(JOURNALS) < 50:
        raise RuntimeError("journal catalog must contain at least 50 journals")
    profiles = [_profile(row) for row in JOURNALS]
    if len({row["id"] for row in profiles}) != len(profiles):
        raise RuntimeError("journal IDs must be unique")
    snapshot = {
        "schema_version": 1,
        "catalog_version": VERSION,
        "reviewed_on": REVIEWED_ON,
        "official_source_policy": (
            "Only publisher or journal author instructions, content definitions, scope pages, and reporting "
            "standards may define submission rules. Unknown numerical limits remain null."
        ),
        "journal_count": len(profiles),
        "journals": profiles,
    }
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_path = OUT_ROOT / f"v{VERSION}.json"
    payload = json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    snapshot_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    index = {
        "schema_version": 1,
        "active_catalog_version": VERSION,
        "active_catalog_file": snapshot_path.name,
        "active_catalog_sha256": digest,
        "reviewed_on": REVIEWED_ON,
        "journal_count": len(profiles),
        "update_policy": {
            "history_is_immutable": True,
            "one_journal_may_advance_independently": True,
            "source_change_requires_new_version": True,
            "unverified_required_field_blocks_submission_ready": True,
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
