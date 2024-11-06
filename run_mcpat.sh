gem5_out_dir='../gem5_with_mcpat/runahead_gem5/m5out'
parser_dir='./gem5_mcpat_parser'
mcpat_input_path='./McPAT_input/mcpat_in.xml'
output_dir='./results/'${3-'McPAT_out'}
python3 ${parser_dir}/Gem5McPATParser_custom.py -c ${gem5_out_dir}/config.json -s ${gem5_out_dir}/stats.txt -t ${parser_dir}/template_x86.xml \
        -o ${mcpat_input_path} \
&& ./mcpat -infile ${mcpat_input_path} -print_level $1 -opt_for_clk $2 | tee ${output_dir}

echo "Results in $output_dir"
