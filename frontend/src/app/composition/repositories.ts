import type {CabinetRepository} from "../../domain/repository";
import {HttpCabinetRepository} from "../../data/repository/cabinet-repository";
export const cabinetRepository:CabinetRepository=new HttpCabinetRepository();
