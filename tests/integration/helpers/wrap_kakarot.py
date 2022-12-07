import json
from pathlib import Path
from typing import cast

from starkware.starknet.testing.starknet import StarknetContract
from web3 import Web3
from web3._utils.abi import map_abi_data
from web3._utils.normalizers import BASE_RETURN_NORMALIZERS
from web3.contract import Contract

from tests.integration.helpers.helpers import hex_string_to_bytes_array
from tests.utils.reporting import traceit


def wrap_for_kakarot(
    contract: Contract, kakarot: StarknetContract, evm_contract_address: int
):
    """
    Wrap a web3.contract to use kakarot as backend.
    """

    def wrap_zk_evm(fun: str, evm_contract_address: int):
        """
        Decorator to update contract.fun to target kakarot instead.
        """

        async def _wrapped(contract, *args, **kwargs):
            abi = contract.get_function_by_name(fun).abi
            if abi["stateMutability"] == "view":
                call = kakarot.execute_at_address(
                    address=evm_contract_address,
                    value=0,
                    calldata=hex_string_to_bytes_array(
                        contract.encodeABI(fun, args, kwargs)
                    ),
                )
                res = await call.call()
            else:
                caller_address = kwargs["caller_address"]
                del kwargs["caller_address"]
                if "value" in kwargs:
                    value = kwargs["value"]
                    del kwargs["value"]
                else:
                    value = 0
                call = kakarot.execute_at_address(
                    address=evm_contract_address,
                    value=value,
                    calldata=hex_string_to_bytes_array(
                        contract.encodeABI(fun, args, kwargs)
                    ),
                )
                res = await call.execute(caller_address=caller_address)
            if call._traced:
                traceit.pop_record()
                traceit.record_tx(
                    res,
                    contract_name=contract._contract_name,
                    attr_name=fun,
                    args=args,
                    kwargs=kwargs,
                )
            types = [o["type"] for o in abi["outputs"]]
            data = bytearray(res.result.return_data)
            decoded = Web3().codec.decode(types, data)
            normalized = map_abi_data(BASE_RETURN_NORMALIZERS, types, decoded)
            return normalized[0] if len(normalized) == 1 else normalized

        return _wrapped

    for fun in contract.functions:
        setattr(
            contract,
            fun,
            classmethod(wrap_zk_evm(fun, evm_contract_address)),
        )
    return contract


def get_contract(contract_name: str) -> Contract:
    """
    Return a web3.contract instance based on the corresponding solidity files
    defined in tests/integration/solidity_files.
    """
    solidity_output_path = Path("tests") / "integration" / "solidity_files" / "output"
    abi = json.load(open(solidity_output_path / f"{contract_name}.abi"))
    bytecode = (solidity_output_path / f"{contract_name}.bin").read_text()
    contract = Web3().eth.contract(abi=abi, bytecode=bytecode)
    setattr(contract, "_contract_name", contract_name)
    return cast(Contract, contract)
