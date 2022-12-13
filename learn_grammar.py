import argparse
import subprocess
import os
import json
import random

random.seed(142857)

POS_MAP = {"NN": "N", "NNP": "N", "PRP": "N", "NNS": "N", "EX": "N",
           "VB": "V", "VBZ": "V", "VBP": "V", "VBD": "V", "MD": "V",
           "JJ": "ADJ", "PRP$": "ADJ", "CD": "ADJ", "JJR": "ADJ", "JJS": "ADJ", "VBN": "ADJ", "VBG": "ADJ",
           "RB": "ADV", "RP": "ADV", "RBR": "ADV", "RBS": "ADV", "CC": "CONJ",
           "DT": "DET", "IN": "PREP",
           "WRB": "CLAUSE", "WP": "CLAUSE", "WDT": "CLAUSE"}  # fine -> coarse parts-of-speech mappings

POS_IGNORE = {",", ".", "TO"}  # parts of speech to ignore

SPLITTERS = {":"}  # sentence splitters

SENTENCE_IGNORE = {"``", "''"}  # ignore sentences having these


def preprocess(data_file, out_dir, small_vocab):
    raw_parsed_output = subprocess.run(["parser/lexparser.sh", data_file], capture_output=True, check=True).stdout
    parsed_output = raw_parsed_output.decode("utf-8")
    parsed_sentences = parsed_output.split("\n\n")[:-1]
    split_sentences = [sentence.split() for sentence in parsed_sentences]

    parts_of_speech = [[word_tag[word_tag.index('/')+1:] for word_tag in sentence] for sentence in split_sentences]

    if small_vocab:
        new_parts_of_speech = []
        for sent_pos in parts_of_speech:
            prev_split = 0
            for i in range(len(sent_pos) + 1):
                if i == len(sent_pos) or sent_pos[i] in SPLITTERS:
                    new_parts_of_speech.append(sent_pos[prev_split:i])
                    prev_split = i + 1
        parts_of_speech = []
        for sent_pos in new_parts_of_speech:
            if not any(pos in SENTENCE_IGNORE for pos in sent_pos):
                parts_of_speech.append([POS_MAP[pos] for pos in sent_pos if pos not in POS_IGNORE])

    with open(os.path.join(out_dir, "data_chars.json"), 'w') as f:
        json.dump(parts_of_speech, f)
    
    vocab = set()
    for sentence in parts_of_speech:
        for word in sentence:
            vocab.add(word)
    
    vocab = list(vocab)
    with open(os.path.join(out_dir, "idx2word.json"), 'w') as f:
        json.dump(vocab, f)
    
    vocab_inv = {word: i for i, word in enumerate(vocab)}
    with open(os.path.join(out_dir, "word2idx.json"), 'w') as f:
        json.dump(vocab_inv, f)
    
    data_idxs = [[vocab_inv[word] for word in sentence] for sentence in parts_of_speech]
    with open(os.path.join(out_dir, "data_idxs.json"), 'w') as f:
        json.dump(data_idxs, f)


def gen_sketch(out_dir, args):
    with open(os.path.join(out_dir, "data_idxs.json"), 'r') as f:
        data = json.load(f)
    
    with open(os.path.join(out_dir, "word2idx.json"), 'r') as f:
        vocab = json.load(f)
    vocab_size = len(vocab)

    sketch = """struct VarRule {
    int k;
    int[2][k] outputs;
}

struct TermRule {
    int k;
    int[k] outputs;
}

struct Grammar {
    int n;
    VarRule[n] var_rules;
    TermRule[n] term_rules;
}

generator Grammar chomsky_grammar(int vocab_size) {
    Grammar grammar = ??;
    int n = grammar.n;
    minimize(n);
    for (int i = 0; i < n; i++) {
        VarRule var_rule = grammar.var_rules[i];
        minimize(var_rule.k);
        for (int j = 0; j < var_rule.k; j++) {
            int B = var_rule.outputs[j][0];
            int C = var_rule.outputs[j][1];
            assert B < n && C < n;
"""
    if not args.relax_chomsky:
        sketch += "            assert B != 0 && C != 0;\n"
    sketch += """        }
        TermRule term_rule = grammar.term_rules[i];
        minimize(term_rule.k);
"""
    if args.restrict_term:
        sketch += "        assert term_rule.k <= 1;\n"
    sketch += """        for (int j = 0; j < term_rule.k; j++) {
            int x = term_rule.outputs[j];
            assert x < vocab_size;
        }
    }
    return grammar;
}

struct Example {
    int L;
    int[L] sentence;
}

harness void check() {
"""
    sketch += f"    Grammar grammar = chomsky_grammar({vocab_size});\n"
    if args.algo == "parse_tree":
        sketch += f"    ParseChoices[{len(data)}] parse_choices = {{" + "??, " * (len(data) - 1) + "??};\n"
    sketch += f"    Example[{len(data)}] examples = {{"
    for i, sentence in enumerate(data):
        sentence_str = str(sentence)[1:-1]
        spaces = "                           " if i else ''
        delim = ',' if i < len(data) - 1 else ''
        L = len(sentence)
        sketch += f"{spaces}new Example(L={L}, sentence={{{sentence_str}}}){delim}\n"
    sketch += "                          };\n"
    
    sketch += f"    for (int i = 0; i < {len(data)}; i++) {{\n"
    if args.algo == "cyk":
        sketch += "         assert grammatical_cyk(grammar, examples[i].sentence);\n"
    else:
        sketch += "         assert grammatical_parse_tree(grammar, examples[i].sentence, parse_choices[i]);\n"
    sketch += "    }\n"

    if args.neg_mode is not None:
        if args.neg_mode == "manual":
            with open(args.neg_data, 'r') as f:
                non_examples = f.read().split('\n')
            non_examples = [[vocab[symbol] for symbol in sentence.split()] for sentence in non_examples]
        else:
            non_examples = []
            for L in range(1, args.max_neg_len):
                num_ex = min(int(vocab_size ** L * args.neg_ratio), args.neg_per_len)
                chosen = set()
                for i in range(num_ex):
                    ex = tuple(random.randint(0, vocab_size-1) for _ in range(L))
                    while ex in chosen:
                        ex = tuple(random.randint(0, vocab_size-1) for _ in range(L))
                    chosen.add(ex)
                    non_examples.append(list(ex))
        
        sketch += f"    Example[{len(non_examples)}] non_examples = {{"
        for i, sentence in enumerate(non_examples):
            sentence_str = str(sentence)[1:-1]
            spaces = "                               " if i else ''
            delim = ',' if i < len(non_examples) - 1 else ''
            L = len(sentence)
            sketch += f"{spaces}new Example(L={L}, sentence={{{sentence_str}}}){delim}\n"
        sketch += ("                          };\n"
                  f"    for (int i = 0; i < {len(non_examples)}; i++) {{\n"
                   "        assert ~grammatical_cyk(grammar, non_examples[i].sentence);\n"
                   "    }\n"
                   "}")
    else:
        sketch += "}"

    if args.algo == "cyk" or args.neg_mode is not None:
        sketch += """

bit grammatical_cyk([int L], Grammar grammar, int[L] sentence) {
    int n = grammar.n;
    bit[n][L][L] table = 0;
    // for each terminal in sentence, mark variables that yield them
    for (int i = 0; i < L; i++) {
        for (int var = 0; var < n; var++) {
            TermRule rule = grammar.term_rules[var];
            for (int j = 0; j < rule.k; j++) {
                if (rule.outputs[j] == sentence[i])
                    table[0][i][var] = 1;
            }
        }
    }
    // DP
    for (int l = 1; l < L; l++) {  // l is length of substring - 1
        for (int i = 0; i < L - l; i++) {  // each length-(l+1) substring of w
            for (int s = 1; s <= l; s++) {  // each way of partitioning substring
                for (int var = 0; var < n; var++) {
                    VarRule rule = grammar.var_rules[var];
                    for (int j = 0; j < rule.k; j++) {  // check all rules
                        int B = rule.outputs[j][0];
                        int C = rule.outputs[j][1];
                        if (table[s-1][i][B] && table[l-s][i+s][C])
                            table[l][i][var] = 1;
                    }
                }
            }
        }
    }
    return table[L-1][0][0];
}
"""
    if args.algo == "parse_tree":
        sketch += """

adt ParseChoices {
    int N;
    int[N] choices;  // binary tree stored in array (similar to heap)
    int[N] sizes;
}

void compute_sizes(ParseChoices parse_choices) {
    int N = parse_choices.N;
    int[N] sizes = parse_choices.sizes;
    for (int i = 0; i < N; i++) {
        int size_l = i < N/2 ? sizes[2*i+1] : 0;
        int size_r = i < (N-1)/2 ? sizes[2*i+2] : 0;
        if (sizes[i] == 1) {
            assert size_l == 0 && size_r == 0;
        } else {
            assert sizes[i] == size_l + size_r;
            if (sizes[i] == 0) {
                assert parse_choices.choices[i] == 0;
            } else {
                assert size_l != 0 && size_r != 0;
            }
        }
    }           
}

bit generates([int L], Grammar grammar, int[L] sentence, ParseChoices parse_choices, int cur_node, int start_var) {
    int N = parse_choices.N;
    int[N] choices = parse_choices.choices;
    int[N] sizes = parse_choices.sizes;
    if (sizes[cur_node] == 1) {  // terminal node
        return L == 1 && sentence[0] == grammar.term_rules[start_var].outputs[choices[cur_node]];
    } else if (sizes[cur_node] != 0) {
        if (L != sizes[cur_node])
            return 0;
        int l = 2*cur_node + 1;
        int r = 2*cur_node + 2;
        int[2] next_vars = grammar.var_rules[start_var].outputs[choices[cur_node]];
        return generates(grammar, sentence[0::sizes[l]], parse_choices, l, next_vars[0]) &&
               generates(grammar, sentence[sizes[l]::sizes[r]], parse_choices, r, next_vars[1]);
    }
}

bit grammatical_parse_tree([int L], Grammar grammar, int[L] sentence, ParseChoices parse_choices) {
    compute_sizes(parse_choices);
    return generates(L, grammar, sentence, parse_choices, 0, 0);
}
"""

    with open(os.path.join(out_dir, "grammar_sketch.sk"), 'w') as f:
        f.write(sketch)


class Args:
    def __init__(self):
        self.small_vocab = True
        self.max_neg_len = 5
        self.neg_ratio = 0.1
        self.neg_per_len = 5


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--do", choices=["all", "preprocess", "gen_sketch"], required=True)
    parser.add_argument("--config", required=True)
    """ CONFIG FILE KEYS
    "name": (required) name of experiment
    "out_dir": (required) directory for output
    "data": (required for `--do all` and `--do preprocess`) path to file containing text data
    "small_vocab": (bool; default: true) whether to replace Stanford Parser parts of speech with coarser categories
    "algo": ("cyk" or "parse_tree") whether to use CYK algorithm or provide parse tree (to be synthesized) to parser;
        only applies to grammatical examples; non-examples always use the CYK algorithm
    "neg_mode": (required; None, "auto", or "manual") whether to use non-examples, and if yes, whether to provide
        manually or to randomly generate
        "neg_data": (required for "neg_mode": "manual") path to file containing non-examples
        "max_neg_len": (for "neg_mode": "auto"; default: 5) max. length of randomly generated non-examples
        "neg_ratio": (for "neg_mode": "auto"; default: 0.1) max. fraction of all sequences of each length
            to select as non-examples
        "neg_per_len": (for "neg_mode": "auto"; default=5) max. no. of sequences of each length to select
            as non-examples
    "restrict_term": (required; bool) whether to forbid a variable from yielding more than 1 terminal
    "relax_chomsky": (required; bool) whether to relax Chomsky normal form to allow start variable on RS of rules
    """

    cl_args = parser.parse_args()
    with open(cl_args.config, 'r') as f:
        config = json.load(f)
    args = Args()
    args.__dict__.update(config)

    path = os.path.join(args.out_dir, args.name)
    os.makedirs(path, exist_ok=True)
    config_path = os.path.join(path, "config.json")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            if json.load(f) != args.__dict__:
                raise Exception(f"Path {path} has already been used on a previous run with a different config!")
    else:
        with open(os.path.join(path, "config.json"), 'w') as f:
            json.dump(args.__dict__, f)

    if cl_args.do == "all":
        preprocess(args.data, path, args.small_vocab)
        gen_sketch(path, args)
    elif cl_args.do == "preprocess":
        preprocess(args.data, path, args.small_vocab)
    else:
        gen_sketch(path, args)
