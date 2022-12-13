# grammar-sketching

This is the repository for my 6.S981 final project: Grammar Learning for Natural Language Syntax.
Here, we formulate grammar learning as a program synthesis problem. Given an example text in a
natural language, we use Sketch to synthesize a context-free grammar
describing the syntax of the language.

Currently, we only support text given in English since the parts-of-speech tagger we use is only for English.

## Setup

Download Sketch 1.7.6 [here](https://people.csail.mit.edu/asolar/) and follow the instructions in the README to install.

Download the Stanford Parser version 4.2.0 [here](https://nlp.stanford.edu/software/lex-parser.shtml#Download).
Unzip it and create a symbolic link named `parser` to the unzipped folder at the root of this repository:
```
user@machine:~/path/to/grammar-sketching$ ln -s /path/to/stanford-parser-full-2020-11-17/ parser
```
The Stanford Parser is used to label words in a sentence with their parts of speech, which are used as input
to the grammar learning algorithm.

## Running the code

First, create a config `.json` file with the following keys:
* `"name"`: (required) name of experiment
* `"out_dir"`: (required) directory for output
* `"data"`: (required for `--do all` and `--do preprocess` - see below) path to file containing text data
* `"small_vocab"`: (bool; default: `true`) whether to replace Stanford Parser parts of speech with coarser categories
* `"algo"`: (`"cyk"` or `"parse_tree"`) whether to use CYK algorithm or provide parse tree (to be synthesized) to parser;
only applies to grammatical examples; non-examples always use the CYK algorithm
* `"neg_mode"`: (required; `null`, `"auto"`, or `"manual"`) whether to use non-examples, and if yes, whether to provide
          manually or to randomly generate
  * `"neg_data"`: (required for `"neg_mode": "manual"`) path to file containing non-examples
  * `"max_neg_len"`: (for `"neg_mode": "auto"`; default: `5`) max. length of randomly generated non-examples
  * `"neg_ratio"`: (for `"neg_mode": "auto"`; default: `0.1`) max. fraction of all sequences of each length
              to select as non-examples
  * `"neg_per_len"`: (for `"neg_mode": "auto"`; default: `5`) max. no. of sequences of each length to select
              as non-examples
* `"restrict_term"`: (required; bool) whether to forbid a variable from yielding more than 1 terminal

Here's an example:
```json
{
    "name": "NV_parse_tree",
    "out_dir": "output",
    "data": "sample_inputs/in_NV.txt",
    "algo": "parse_tree",
    "neg_mode": null,
    "restrict_term": false
}
```

Note that the [`sample_inputs`](sample_inputs/) folder contains some sample input text files.

Now, simply run
```
python learn_grammar.py --do all --config path/to/config.json
```
to generate a Sketch file located at `path/to/output/directory/grammar_sketch.sk`. You can then
run the Sketch synthesizer to synthesize the CFG describing the input text:
```
sketch path/to/output/directory/grammar_sketch.sk
```
You might need to pass an argument `--bnd-unroll-amnt N` where `N` is some large number such as 25 for the synthesis to work.
You can use the flag `-V` with an integer argument to increase the verbosity.

The synthesized program contains assignments to `var_rules` and `term_rules`, which encode rules
of the form `A -> BC` and `A -> a`, respectively. (The grammar is in Chomsky normal form.)
Variables and terminals are represented as integers. The encoding for terminals is given in
`path/to/output/directory/word2idx.json`.
* `var_rules` is an array where the element at index `A` is a `VarRule` object, which stores
an array of pairs `{B, C}` such that `A -> BC` is a rule.
* `term_rules` is an array where the element at index `A` is a `TermRule` object, which stores
an array of elements `a` such that `A -> a` is a rule.

Instead of using the `--do all` option with `python learn_grammar.py`, you can also run the code with the `--do preprocess`
option and then run it with the `--do gen_sketch` option, which has the same effect. In particular,
```
python learn_grammar.py --do preprocess --config path/to/config.json
```
preprocesses the data by converting all words into their parts of speech. Afterwards,
```
python learn_grammar.py --do gen_sketch --config path/to/config.json
```
generates the Sketch file.
